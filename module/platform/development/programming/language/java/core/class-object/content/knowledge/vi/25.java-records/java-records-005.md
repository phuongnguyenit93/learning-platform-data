# Record: kiểm tra, chuẩn hóa dữ liệu và sao chép phòng vệ trong Java 17+

Trong Java 17, `record` giúp mô hình hóa **đối tượng mang dữ liệu** bằng cách khai báo các *components*. Java tự tạo private final fields, public accessors, canonical constructor, `equals`, `hashCode` và `toString` khi bạn không tự cung cấp các thành phần đó.

~~~java
record User(String name, int age) {}
~~~

Tuy nhiên, **record không tự kiểm tra dữ liệu, chuẩn hóa chuỗi hay sao chép object mutable**. Nếu bạn chỉ viết `record User(String name, int age) {}`, chương trình có thể tạo `new User(null, -10)`. Nếu record chứa `List`, `Map`, array hoặc object mutable, việc các component fields là `final` **không tự làm dữ liệu bên trong bất biến**.

Bài này tập trung vào ba trách nhiệm quan trọng của *record constructor/accessor*:

1. **Validation:** từ chối đầu vào vi phạm điều kiện nghiệp vụ bằng exception đúng.
2. **Normalization:** đưa nhiều cách biểu diễn tương đương về một dạng thống nhất trước khi lưu.
3. **Defensive copying:** ngăn caller sửa state của record qua aliases tới dữ liệu mutable.

Đây là một README tự học độc lập cho **Java Core — Class & Object / Record** với **Java 17+**. Chương trình hoàn chỉnh có tên file, lệnh `javac`/`java` và stdout dự kiến; snippets chỉ minh họa được nêu rõ.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Viết record với **compact canonical constructor**.
- Phân biệt compact constructor và explicit canonical constructor.
- Kiểm tra null, blank, range, quan hệ giữa components và business invariants.
- Chuẩn hóa chuỗi `strip()`, case với `Locale.ROOT` và dữ liệu cấu trúc.
- Hiểu normalization khác validation và phải đúng domain.
- Biết không được gán `this.component = ...` trong compact constructor.
- Thực hiện kiểm tra trước khi state hợp lệ được công bố qua object.
- Chọn `IllegalArgumentException` và `NullPointerException` có chủ đích.
- Dùng `List.copyOf`, `Set.copyOf`, `Map.copyOf` đúng giới hạn.
- Hiểu *snapshot* khác *unmodifiable live view*.
- Phân biệt shallow copy và deep copy với phần tử mutable.
- Bảo vệ component arrays bằng `clone()` ở constructor **và accessor**.
- Nhận diện khi default `equals/hashCode/toString` không phù hợp với array.
- Bảo vệ record được dùng làm `HashMap` key khỏi biến đổi bất ngờ.
- Chọn immutable components của `java.time` thay vì mutable legacy types khi hợp lý.
- Thiết kế record chứa nested records, collections và payload dữ liệu.
- Kiểm thử valid/invalid/edge input, normalization, aliasing và equality contract.
- Phân biệt lỗi phổ biến trong constructor, accessor và factory.
- Quyết định khi nào record phù hợp và khi nào nên dùng class thông thường.

## 2. Record tạo ra gì?

Với declaration:

~~~java
record Point(int x, int y) {}
~~~

Java cung cấp tương đương về mặt sử dụng:

- private final fields `x` và `y`;
- accessor methods `int x()` và `int y()`;
- public/package-appropriate canonical constructor `Point(int x, int y)` theo access rules;
- `equals(Object)` so sánh các record components theo record rules;
- `hashCode()` tính từ các components;
- `toString()` thể hiện tên record và các component values.

Một record implicitly extends `java.lang.Record` và không thể extends class khác tùy ý. Nó có thể implements interfaces.

**Quan trọng:** `final` ở fields chỉ chặn **gán lại reference/value của field** sau initialization. Nó không tự kiểm soát object mutable mà một field đang trỏ tới.

~~~java
record Group(java.util.List<String> members) {}
~~~

Nếu caller đưa một `ArrayList` vào `new Group(list)`, component `members` giữ reference tới cùng List object nếu record không copy.

## 3. Bắt đầu với validation trong compact constructor

Một **compact constructor** có dạng:

~~~java
record Person(String name, int age) {
    Person {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("age out of range");
        }
    }
}
~~~

Bạn không khai báo parameter list ở `Person { ... }`, nhưng Java cho phép dùng parameters có tên theo record components: `name`, `age`. Khi compact constructor body kết thúc bình thường, **compiler tự gán final fields từ các parameter values cuối cùng**.

Điểm mạnh: bạn chỉ đặt validation/normalization cần thiết, không lặp boilerplate `this.name = name`.

### Quy tắc then chốt

Trong compact constructor, **không gán trực tiếp component field**:

~~~java
record Invalid(String name) {
    Invalid {
        // this.name = name; // Lỗi biên dịch với compact constructor.
    }
}
~~~

Muốn thay giá trị lưu vào component, **gán lại parameter** `name = ...`.

## 4. Chương trình chạy: constructor từ chối dữ liệu không hợp lệ

Tạo **`RecordValidationDemo.java`**:

~~~java
public class RecordValidationDemo {
    record Person(String name, int age) {
        Person {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("age");
            }
        }
    }

    public static void main(String[] args) {
        Person ok = new Person("Mai", 20);
        System.out.println(ok);

        try {
            new Person(" ", 20);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        try {
            new Person("An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordValidationDemo.java
java RecordValidationDemo
~~~

Stdout:

~~~text
Person[name=Mai, age=20]
invalid=name
invalid=age
~~~

Một lần `new Person(...)` vi phạm invariant thì constructor ném exception; expression tạo record **không trả một instance hợp lệ** cho caller.

## 5. Validation và normalization khác nhau

**Validation** trả lời: “Đầu vào này được chấp nhận không?”

**Normalization** trả lời: “Nếu được chấp nhận, dạng chuẩn nào cần được lưu?”

Ví dụ input `"  Mai  "`:

- Validation có thể từ chối null hoặc toàn whitespace.
- Normalization có thể dùng `strip()` để lưu `"Mai"`.
- Nếu domain cho phép tên có khoảng trắng hai đầu, tự `strip` có thể **thay đổi ý nghĩa dữ liệu** ngoài mong muốn; cần định nghĩa rõ policy.

Với mã định danh `"  AbC  "`, có domain muốn normalize thành `"abc"`, domain khác yêu cầu giữ case. **Không tự lower-case mọi chuỗi** chỉ vì API hỗ trợ.

Thứ tự hợp lý thường là:
1. xác định null policy;
2. normalize vào dạng tạm;
3. validate dạng chuẩn;
4. chỉ lưu giá trị đã hợp lệ.

## 6. Compact constructor chuẩn hóa bằng cách gán parameter

~~~java
record Account(String username) {
    Account {
        username = java.util.Objects.requireNonNull(
                username, "username").strip()
                .toLowerCase(java.util.Locale.ROOT);

        if (username.isEmpty()) {
            throw new IllegalArgumentException("blank username");
        }
    }
}
~~~

`username = ...` ở compact constructor là **reassignment của constructor parameter**, không phải gán trực tiếp field. Sau constructor body, Java tự gán record field từ giá trị đã chuẩn hóa.

### Vì sao dùng `Locale.ROOT`?

Các thao tác case conversion có thể phụ thuộc locale. Với **technical identifiers** cần hành vi ổn định, `Locale.ROOT` thường phù hợp hơn default system locale. Với tên người, ngôn ngữ tự nhiên, thông tin định danh theo locale thực tế, quy tắc phải theo domain — không áp dụng một chuyển đổi chung máy móc.

## 7. Chương trình chạy: chuẩn hóa username

Tạo **`RecordNormalizationDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class RecordNormalizationDemo {
    record Account(String username) {
        Account {
            username = Objects.requireNonNull(
                    username, "username")
                    .strip()
                    .toLowerCase(Locale.ROOT);

            if (username.isBlank()) {
                throw new IllegalArgumentException("username blank");
            }
        }
    }

    public static void main(String[] args) {
        Account first = new Account("  ADMIN  ");
        Account second = new Account("admin");

        System.out.println(first.username());
        System.out.println("equal=" + first.equals(second));

        try {
            new Account("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordNormalizationDemo.java
java RecordNormalizationDemo
~~~

Stdout:

~~~text
admin
equal=true
invalid=username blank
~~~

Hai inputs khác textual representation nhưng trở thành cùng canonical username. Vì vậy default record `equals/hashCode` nay hoạt động phù hợp với **normalized field values**.

## 8. Chuẩn hóa trước hay kiểm tra trước?

Không có một thứ tự duy nhất đúng cho mọi domain.

Ví dụ:

~~~java
String normalized = Objects.requireNonNull(raw, "raw").strip();
if (normalized.isEmpty()) {
    throw new IllegalArgumentException("blank");
}
~~~

Nếu business rule cấm whitespace ở hai đầu, bạn **không nên tự strip trước rồi chấp nhận**, mà cần validate raw input:

~~~java
if (!raw.equals(raw.strip())) {
    throw new IllegalArgumentException("leading/trailing spaces");
}
~~~

Quy tắc cần được đặc tả:

| Chính sách | Input `" A "` | Kết quả |
| --- | --- | --- |
| Normalize whitespace | Được chấp nhận | Lưu `"A"` |
| Strict identifier | Bị từ chối | Exception |
| Text verbatim | Được chấp nhận | Lưu `" A "` |

Đừng viết normalize policy quá rộng làm mất dữ liệu quan trọng như email local-part, mã case-sensitive hoặc khoảng trắng chủ đích.

## 9. Kiểm tra nhiều components cùng lúc

Records có thể chứa các components có **ràng buộc liên đới**.

~~~java
record DateRange(java.time.LocalDate start,
                 java.time.LocalDate end) {
    DateRange {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not precede start");
        }
    }
}
~~~

Đây là invariant trên **cặp start/end**, không thể kiểm tra đầy đủ từng field độc lập.

Nhờ `LocalDate` immutable, không cần defensive clone dates. Nếu dùng mutable `java.util.Date`, vấn đề sẽ khác.

## 10. Chương trình chạy: record DateRange

Tạo **`RecordDateRangeDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public class RecordDateRangeDemo {
    record DateRange(LocalDate start, LocalDate end) {
        DateRange {
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(end, "end");

            if (end.isBefore(start)) {
                throw new IllegalArgumentException("range");
            }
        }

        long daysInclusive() {
            return java.time.temporal.ChronoUnit.DAYS
                    .between(start, end) + 1;
        }
    }

    public static void main(String[] args) {
        DateRange valid = new DateRange(
                LocalDate.of(2026, 10, 1),
                LocalDate.of(2026, 10, 3));

        System.out.println("days=" + valid.daysInclusive());

        try {
            new DateRange(
                    LocalDate.of(2026, 10, 3),
                    LocalDate.of(2026, 10, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordDateRangeDemo.java
java RecordDateRangeDemo
~~~

Stdout:

~~~text
days=3
invalid=range
~~~

`daysInclusive` là instance method hợp lệ của record. Record phù hợp vì range là một value object đơn giản với invariants rõ.

## 11. Chính sách exception cho invalid input

Phổ biến:

- `Objects.requireNonNull(value, "field")` → `NullPointerException` với message khi input null; phù hợp khi null bị cấm theo contract.
- `IllegalArgumentException` → dữ liệu có type đúng nhưng sai domain rule (blank, negative, range).
- Custom unchecked exception → chỉ khi API/domain có contract nhất quán và caller cần phân loại riêng.
- Checked exceptions → cân nhắc ở boundary có IO/external operation, không phải validation thuần.

Ví dụ:

~~~java
record Quantity(int value) {
    Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}
~~~

**Không dùng `assert` để validate user input**: Java assertions có thể bị disable khi chạy. Public invariants cần kiểm tra bằng bình thường và ném exception.

## 12. Chương trình chạy: phân biệt null và blank

Tạo **`RecordExceptionPolicyDemo.java`**:

~~~java
import java.util.Objects;

public class RecordExceptionPolicyDemo {
    record Category(String code) {
        Category {
            code = Objects.requireNonNull(code, "code").strip();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("blank code");
            }
        }
    }

    public static void main(String[] args) {
        try {
            new Category(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getMessage());
        }

        try {
            new Category("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("blank=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordExceptionPolicyDemo.java
java RecordExceptionPolicyDemo
~~~

Stdout:

~~~text
null=code
blank=blank code
~~~

API phân biệt null với value blank; consumer có thể xử lý errors theo hợp đồng rõ ràng.

## 13. Compact vs explicit canonical constructor

Có hai hình thức chuẩn:

**Compact canonical constructor**:

~~~java
record Email(String address) {
    Email {
        address = address.strip();
    }
}
~~~

**Explicit canonical constructor**:

~~~java
record Email(String address) {
    Email(String address) {
        this.address = address.strip();
    }
}
~~~

Trong explicit canonical constructor:
- parameter list phải khớp các record components theo canonical constructor rules;
- bạn phải gán từng component field đúng một cách hợp lệ trước khi constructor kết thúc;
- có thể chủ động xác định trình tự logic gán, nhưng Java final-field/definite-assignment rules vẫn áp dụng.

Trong compact constructor, compiler đảm nhiệm field assignments sau body. **Đừng viết cả hai canonical constructor forms đồng thời** cho cùng signature.

## 14. Chương trình chạy: hai cách viết tương đương

Tạo **`CanonicalFormsDemo.java`**:

~~~java
public class CanonicalFormsDemo {
    record Compact(String code) {
        Compact {
            code = code.strip();
        }
    }

    record Explicit(String code) {
        Explicit(String code) {
            this.code = code.strip();
        }
    }

    public static void main(String[] args) {
        Compact a = new Compact(" A ");
        Explicit b = new Explicit(" A ");

        System.out.println("compact=" + a.code());
        System.out.println("explicit=" + b.code());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CanonicalFormsDemo.java
java CanonicalFormsDemo
~~~

Stdout:

~~~text
compact=A
explicit=A
~~~

Ở ví dụ ngắn, compact constructor tránh boilerplate. Khi cần explicit canonical constructor vì lý do hợp lệ, phải xử lý assignments đầy đủ và nhất quán.

## 15. Record không đồng nghĩa deep immutable

Xét:

~~~java
record Team(java.util.List<String> members) {}
~~~

Tạo bằng ArrayList:

~~~java
java.util.List<String> original =
        new java.util.ArrayList<>(java.util.List.of("Mai"));

Team team = new Team(original);
original.add("An");
~~~

Vì record mặc định giữ **cùng List reference** trong `members`, `team.members()` có thể bây giờ chứa Mai và An.

Tính bất biến cần phân biệt:
- **Field immutability:** final record component field không reassign được.
- **Shallow structural immutability:** collection object không được sửa qua exposed reference.
- **Deep immutability:** cả elements/nested mutable objects không bị sửa ngoài ý muốn.
- **Snapshot semantics:** record giữ dữ liệu ở một thời điểm, không live-follow external collection.

Không thể suy ra deep immutability chỉ từ keyword `record`.

## 16. Chương trình chạy: lỗi aliasing khi không copy

Tạo **`BadRecordAliasingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BadRecordAliasingDemo {
    record Team(List<String> members) {}

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Mai");

        Team team = new Team(source);
        System.out.println("before=" + team.members());

        source.add("An");
        System.out.println("after=" + team.members());

        team.members().add("Binh");
        System.out.println("source=" + source);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BadRecordAliasingDemo.java
java BadRecordAliasingDemo
~~~

Stdout:

~~~text
before=[Mai]
after=[Mai, An]
source=[Mai, An, Binh]
~~~

Hai hướng mutate đều có thể ảnh hưởng cùng object. Đây là anti-pattern khi record được kỳ vọng đại diện cho một snapshot.

## 17. Sao chép phòng vệ collection bằng `List.copyOf`

~~~java
record Team(java.util.List<String> members) {
    Team {
        members = java.util.List.copyOf(
                java.util.Objects.requireNonNull(members, "members"));
    }
}
~~~

`List.copyOf`:
- tạo **unmodifiable list** chứa các elements của input ở thời điểm gọi, theo list iteration order;
- không phản ánh những structural changes sau này của mutable source;
- từ chối null elements bằng `NullPointerException`;
- có thể reuse một existing unmodifiable list thay vì luôn allocate List mới;
- **không deep-copy elements**.

Nếu elements là immutable Strings, snapshot cấu trúc danh sách thường đã đủ.

**Quan trọng:** `List.copyOf` không chỉ tạo một view live của ArrayList gốc. Nó có snapshot semantics cho collection structure.

## 18. Chương trình chạy: List.copyOf bảo vệ hai hướng

Tạo **`RecordListCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RecordListCopyDemo {
    record Team(List<String> members) {
        Team {
            members = List.copyOf(
                    Objects.requireNonNull(members, "members"));
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Mai");

        Team team = new Team(source);
        source.add("An");

        System.out.println("source=" + source);
        System.out.println("record=" + team.members());

        try {
            team.members().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("record list unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordListCopyDemo.java
java RecordListCopyDemo
~~~

Stdout:

~~~text
source=[Mai, An]
record=[Mai]
record list unmodifiable
~~~

Input changes không làm record list thay đổi; accessor trả unmodifiable list, nên caller không thêm element qua accessor được.

## 19. `List.copyOf` và chính sách null elements

~~~java
List<String> list = new ArrayList<>();
list.add(null);
List.copyOf(list); // Ném NullPointerException.
~~~

`List.copyOf` cấm **null elements**, khác với một số cách tạo List thông thường. Vì vậy cần xác định null policy:

- Nếu elements không được null: List.copyOf là lựa chọn phù hợp.
- Nếu null có ý nghĩa domain: phải cân nhắc một representation khác hoặc dùng snapshot wrapper cho phép null.
- Nếu chỉ muốn bỏ qua null: cần yêu cầu rõ; đừng âm thầm filter invalid elements nếu điều đó làm mất dữ liệu.

Ví dụ snapshot có null nhưng unmodifiable:

~~~java
List<String> snapshot = java.util.Collections.unmodifiableList(
        new java.util.ArrayList<>(source));
~~~

Cách này copy cấu trúc rồi bọc unmodifiable, nhưng vẫn là **shallow copy**.

## 20. `Collections.unmodifiableList` có phải defensive snapshot?

Không nếu chỉ bọc trực tiếp một mutable list:

~~~java
List<String> source = new ArrayList<>();
List<String> view = Collections.unmodifiableList(source);
source.add("A");
// view sẽ phản ánh "A".
~~~

`unmodifiableList(source)` tạo **view không cho mutate qua reference view**, nhưng underlying source vẫn mutable bởi người giữ reference khác.

Để tạo snapshot wrapper:

~~~java
List<String> stable = Collections.unmodifiableList(
        new ArrayList<>(source));
~~~

Một thay đổi về structure của source sau đó không ảnh hưởng stable, bởi stable được bọc trên **copy**. Nhưng elements nếu mutable vẫn được chia sẻ references.

Nếu null không cần cho phép, `List.copyOf(source)` thường ngắn và rõ.

## 21. Chương trình chạy: live view khác snapshot

Tạo **`UnmodifiableViewDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> live = Collections.unmodifiableList(source);
        List<String> copied = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("live=" + live);
        System.out.println("copied=" + copied);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UnmodifiableViewDemo.java
java UnmodifiableViewDemo
~~~

Stdout:

~~~text
source=[A, B]
live=[A, B]
copied=[A]
~~~

`live` là unmodifiable view nhưng vẫn thấy structural mutations của source. `copied` có snapshot behavior.

## 22. `Set.copyOf` và `Map.copyOf`

Records thường có collections khác List:

~~~java
record Config(java.util.Set<String> flags,
              java.util.Map<String, String> settings) {
    Config {
        flags = java.util.Set.copyOf(flags);
        settings = java.util.Map.copyOf(settings);
    }
}
~~~

`Set.copyOf` tạo unmodifiable set snapshot và cấm null elements. `Map.copyOf` tạo unmodifiable map snapshot, cấm null keys/values.

**Cẩn trọng ordering:**
- `Set.copyOf` không đảm bảo encounter/iteration order như List.
- `Map.copyOf` không hứa insertion order.
- Nếu thứ tự cần nằm trong contract/API, chọn collection và copying strategy phù hợp.

Dù set/map structure không mutate được, **objects stored as elements/keys/values vẫn có thể mutable**.

## 23. Chương trình chạy: Map.copyOf giữ snapshot

Tạo **`RecordMapCopyDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class RecordMapCopyDemo {
    record Settings(Map<String, String> entries) {
        Settings {
            entries = Map.copyOf(entries);
        }
    }

    public static void main(String[] args) {
        Map<String, String> source = new LinkedHashMap<>();
        source.put("theme", "dark");

        Settings snapshot = new Settings(source);
        source.put("language", "vi");

        System.out.println("snapshot size=" + snapshot.entries().size());
        System.out.println("source size=" + source.size());
        System.out.println("theme=" + snapshot.entries().get("theme"));

        try {
            snapshot.entries().put("x", "y");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordMapCopyDemo.java
java RecordMapCopyDemo
~~~

Stdout:

~~~text
snapshot size=1
source size=2
theme=dark
unmodifiable
~~~

Ví dụ không in toàn bộ Map vì thứ tự duyệt của Map.copyOf không phải phần cần giả định.

## 24. Sao chép cấu trúc vẫn chưa phải deep copy

Một record chứa `List<MutableItem>` có thể được xây bằng `List.copyOf`, nhưng elements vẫn là **same objects**:

~~~java
record Order(java.util.List<MutableItem> items) {
    Order {
        items = java.util.List.copyOf(items);
    }
}
~~~

Nếu caller giữ `MutableItem item` và thay `item.value`, record nhìn qua `order.items().get(0)` cũng có thể thấy thay đổi.

Do đó:
- `List.copyOf` **snapshot List structure**, không clone elements.
- Muốn deep immutability, mỗi element phải immutable hoặc được snapshot thành immutable value object.
- Nếu có nested collections, cần copy ở từng level cần bảo vệ.

Không nên gọi `List.copyOf` là “deep copy”; nó không làm điều đó.

## 25. Chương trình chạy: mutable element vẫn thay đổi

Tạo **`ShallowCopyPitfallDemo.java`**:

~~~java
import java.util.List;

public class ShallowCopyPitfallDemo {
    static final class MutableScore {
        int points;

        MutableScore(int points) {
            this.points = points;
        }
    }

    record Report(List<MutableScore> scores) {
        Report {
            scores = List.copyOf(scores);
        }
    }

    public static void main(String[] args) {
        MutableScore item = new MutableScore(10);
        Report report = new Report(List.of(item));

        System.out.println("before=" + report.scores().get(0).points);

        item.points = 99;
        System.out.println("after=" + report.scores().get(0).points);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ShallowCopyPitfallDemo.java
java ShallowCopyPitfallDemo
~~~

Stdout:

~~~text
before=10
after=99
~~~

List structure bất biến nhưng element object thay đổi. Nếu domain cần snapshot thực sự, phải đổi representation hoặc copy elements.

## 26. Deep snapshot bằng nested immutable record

Một hướng an toàn là chuyển mỗi mutable DTO thành **immutable record**:

~~~java
record Score(String student, int points) {}

record GradeBook(java.util.List<Score> scores) {
    GradeBook {
        scores = java.util.List.copyOf(scores);
    }
}
~~~

Nếu `Score` chỉ chứa String và int (và đã validate), Score objects bất biến về cấu trúc và không có mutable references bên trong. Vì vậy `List.copyOf` cho snapshot list khá mạnh.

Khi input là mutable objects, map chúng sang Score record mới:

~~~java
scores = source.stream()
        .map(item -> new Score(item.student(), item.points()))
        .toList();
~~~

`Stream.toList()` cho unmodifiable list (Java 16+), nhưng khác `List.copyOf` về null policy: `toList()` không có cùng đảm bảo cấm null elements. Nếu cần null-free policy, validate/truyền qua List.copyOf.

## 27. Chương trình chạy: deep-copy mutable inputs thành immutable values

Tạo **`DeepSnapshotRecordDemo.java`**:

~~~java
import java.util.List;

public class DeepSnapshotRecordDemo {
    static final class MutableScore {
        String student;
        int points;

        MutableScore(String student, int points) {
            this.student = student;
            this.points = points;
        }
    }

    record Score(String student, int points) {
        Score {
            if (student == null || student.isBlank()) {
                throw new IllegalArgumentException("student");
            }
            if (points < 0 || points > 100) {
                throw new IllegalArgumentException("points");
            }
        }
    }

    record GradeBook(List<Score> scores) {
        GradeBook {
            scores = List.copyOf(scores);
        }

        static GradeBook fromMutable(List<MutableScore> source) {
            List<Score> snapshots = source.stream()
                    .map(item -> new Score(item.student, item.points))
                    .toList();

            return new GradeBook(snapshots);
        }
    }

    public static void main(String[] args) {
        MutableScore source = new MutableScore("Mai", 10);
        GradeBook book = GradeBook.fromMutable(List.of(source));

        source.points = 99;

        System.out.println("source=" + source.points);
        System.out.println("snapshot=" + book.scores().get(0).points());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DeepSnapshotRecordDemo.java
java DeepSnapshotRecordDemo
~~~

Stdout:

~~~text
source=99
snapshot=10
~~~

Vì mỗi Score mới không chứa mutable object, thay đổi MutableScore sau đó không ảnh hưởng GradeBook.

## 28. Nếu nested record chứa mutable data thì sao?

Một nested record **không tự deep immutable** nếu chính nó chứa array/List mutable.

~~~java
record Image(byte[] pixels) {}
record Album(java.util.List<Image> images) {}
~~~

Dù `Album.images` dùng List.copyOf, `Image.pixels()` vẫn lộ mutable array nếu Image không có defensive copying.

**Quy tắc đệ quy:** Muốn bất biến sâu phải kiểm tra **cả đường reference** tới mutable objects. Các lớp record lồng nhau không tự “niêm phong” objects.

Có thể dùng:
- immutable primitives, String, enum, java.time classes;
- collections of immutable elements;
- records có defensive-copy rules riêng;
- explicit deep copy cho mutable substructures.

## 29. Array: copy ở constructor là chưa đủ

Record với array:

~~~java
record Blob(byte[] bytes) {}
~~~

Array là mutable, nên caller có thể:
1. sửa array gốc sau khi tạo Blob;
2. lấy `blob.bytes()` và sửa array qua accessor mặc định.

Chỉ copy ở input **chặn hướng 1**, không chặn hướng 2. Nếu record phải bảo vệ dữ liệu:

~~~java
record Blob(byte[] bytes) {
    Blob {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

`clone()` cho primitive array tạo một independent array copy. Nên dùng `Objects.requireNonNull(bytes,"bytes")` trước để có message rõ; `bytes.clone()` tự ném NPE nếu bytes null nhưng thông báo có thể khác.

## 30. Chương trình chạy: copy cả hai hướng cho array

Tạo **`RecordArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class RecordArrayCopyDemo {
    record Blob(byte[] bytes) {
        Blob {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Blob blob = new Blob(input);

        input[0] = 9;
        System.out.println("after source change=" +
                Arrays.toString(blob.bytes()));

        byte[] exposed = blob.bytes();
        exposed[1] = 8;
        System.out.println("after getter change=" +
                Arrays.toString(blob.bytes()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordArrayCopyDemo.java
java RecordArrayCopyDemo
~~~

Stdout:

~~~text
after source change=[1, 2, 3]
after getter change=[1, 2, 3]
~~~

Record giữ array copy riêng và accessor trả thêm copy. Đó là defensive copying của mutable array component.

## 31. Nhưng array component còn vấn đề `equals` và `hashCode`

Record-generated equality so sánh các components theo semantics của component types. Với array component, mặc định **không phải element-wise equality** như `Arrays.equals`, mà array references được so sánh theo identity.

Vì vậy:

~~~java
record Blob(byte[] bytes) {
    Blob {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Hai Blobs có same byte content nhưng chứa **hai array objects khác nhau**; generated `equals` có thể trả false. `toString` cũng không tự in arrays đẹp theo element content.

Nếu domain cần **value equality theo bytes**, override `equals`, `hashCode` và tùy chọn `toString` nhất quán.

## 32. Record đã copy array vẫn chưa tự có value equality

Giả sử hai instances được xây từ các array `new byte[]{1,2}` riêng biệt. Mỗi compact constructor đã clone đầu vào và accessor cũng clone đầu ra, nên **ownership an toàn**; nhưng generated `equals` mặc định vẫn so hai array component references, dẫn đến false dù byte contents bằng nhau.

~~~java
record Blob(byte[] bytes) {
    Blob {
        bytes = bytes.clone();
    }
    @Override public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Đây là **record declaration** không có `main`. Với `Blob a = new Blob(new byte[]{1,2}); Blob b = new Blob(new byte[]{1,2});`, `a.equals(b)` là false, còn `Arrays.equals(a.bytes(), b.bytes())` là true.

Ở bài **validation/defensive copying**, bài học là **copy chống aliasing không đồng nghĩa đổi equality**. Các chương trình test đầy đủ, hash contract và identity behavior thuộc bài riêng **“equals(), hashCode(), toString() và ảnh hưởng của thành phần mảng”**.

## 33. Khi domain yêu cầu so nội dung mảng

Nếu `byte[]` biểu diễn **giá trị** (thay vì identity của buffer), cần xác định thêm contract của `equals` và `hashCode`. Chẳng hạn, trong body của record `Blob(byte[] bytes)` đã phòng vệ đúng cả hai chiều, có thể viết:

~~~java
@Override
public boolean equals(Object other) {
    return other instanceof Blob blob
            && java.util.Arrays.equals(bytes, blob.bytes);
}

@Override
public int hashCode() {
    return java.util.Arrays.hashCode(bytes);
}
~~~

Đây chỉ là **đoạn member-method bổ sung bên trong record**, không phải một file runnable độc lập. Với một mảng một chiều, `Arrays.equals` và `Arrays.hashCode` giữ hai methods nhất quán. Nếu dữ liệu là nested arrays thì cần xét `deepEquals`/`deepHashCode` và việc deep copy tương ứng. `toString` có thể tùy chỉnh khi muốn hiển thị nội dung thay vì array identity string.

**Điểm chính:** constructor có trách nhiệm **validate, normalize và bảo vệ ownership**. Các chính sách equality/hash sâu thuộc mô hình giá trị và được học/kiểm thử đầy đủ ở bài chuyên đề về generated methods với array components. Không override chỉ `equals` mà bỏ `hashCode`.

## 34. Object arrays và multidimensional arrays

Với `String[]`, `clone()` tạo array mới nhưng references tới elements vẫn được chia sẻ. Nếu elements là immutable Strings, đó thường là đủ. Với `MutableItem[]`, shallow array clone chưa copy elements.

Với `int[][]`, chỉ gọi `matrix.clone()` copy **outer array**; mỗi inner `int[]` vẫn bị chia sẻ. Muốn deep snapshot 2D primitive array:

~~~java
static int[][] copyMatrix(int[][] input) {
    int[][] result = new int[input.length][];
    for (int i = 0; i < input.length; i++) {
        result[i] = input[i].clone();
    }
    return result;
}
~~~

Đây là snippet chỉ minh họa; production code cần explicit null policy cho input/rows và equality/content display strategy.

Nếu nested data structure quá mutable/phức tạp, cân nhắc custom immutable class với rõ contract thay vì mặc định một record với arrays.

## 35. Chương trình chạy: deep-copy 2D int array

Tạo **`MatrixRecordDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class MatrixRecordDemo {
    record Matrix(int[][] rows) {
        Matrix {
            rows = deepCopy(rows);
        }

        @Override
        public int[][] rows() {
            return deepCopy(rows);
        }

        private static int[][] deepCopy(int[][] source) {
            Objects.requireNonNull(source, "rows");
            int[][] result = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                result[i] = Objects.requireNonNull(
                        source[i], "row " + i).clone();
            }
            return result;
        }

        int at(int row, int column) {
            return rows[row][column];
        }
    }

    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3, 4}};
        Matrix matrix = new Matrix(input);

        input[0][0] = 99;
        int[][] output = matrix.rows();
        output[1][1] = 88;

        System.out.println("at00=" + matrix.at(0, 0));
        System.out.println("at11=" + matrix.at(1, 1));
        System.out.println("snapshot=" +
                Arrays.deepToString(matrix.rows()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MatrixRecordDemo.java
java MatrixRecordDemo
~~~

Stdout:

~~~text
at00=1
at11=4
snapshot=[[1, 2], [3, 4]]
~~~

Vẫn cần override equals/hashCode nếu muốn Matrix value equality theo nội dung 2D arrays. `Arrays.deepEquals/deepHashCode` cung cấp công cụ phù hợp khi dữ liệu là nested arrays.

## 36. Vấn đề mutable key của Map và Set

Khi một record dùng `equals/hashCode` dựa trên mutable component objects, thay đổi object bên ngoài có thể làm hash code record thay đổi sau khi record đã được dùng làm `HashMap` key.

Ví dụ:

~~~java
record Key(java.util.List<String> tags) {}
~~~

Nếu tags là mutable ArrayList, việc thêm tag sau khi insert Key vào HashMap làm component list hash code thay đổi. Lookup bằng cùng Key reference có thể thất bại vì bucket phụ thuộc hash cũ.

**Record fields final không tự ngăn điều này.**

### Giải pháp

- Normalize và defensive-copy collection trong canonical constructor.
- Chỉ lưu immutable elements.
- Với arrays, clone + content equality/hash khi muốn value semantics.
- Không mutate components của key sau khi tạo.

## 37. Chương trình chạy: record key với copied List

Tạo **`RecordMapKeyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class RecordMapKeyDemo {
    record Key(List<String> tags) {
        Key {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("java");

        Key key = new Key(input);
        Map<Key, String> lookup = new HashMap<>();
        lookup.put(key, "present");

        input.add("record");

        System.out.println("key tags=" + key.tags());
        System.out.println("found=" + lookup.get(key));
        System.out.println("same-value lookup=" +
                lookup.get(new Key(List.of("java"))));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordMapKeyDemo.java
java RecordMapKeyDemo
~~~

Stdout:

~~~text
key tags=[java]
found=present
same-value lookup=present
~~~

List snapshot với immutable Strings giúp record equality/hash ổn định theo value.

## 38. Chuẩn hóa Unicode: chỉ làm khi contract yêu cầu

Hai strings có thể hiển thị giống nhau nhưng có Unicode code-point sequences khác nhau. Nếu domain cần canonical Unicode text, Java cung cấp:

~~~java
java.text.Normalizer.normalize(
        input, java.text.Normalizer.Form.NFC);
~~~

`NFC` là một Unicode normalization form. Nhưng không phải mọi field đều nên normalize Unicode:
- File paths, credentials, cryptographic signatures hoặc binary-like identifiers có thể yêu cầu exact bytes/code points.
- Search/display names có thể muốn normalization khác.
- Một số domain cần case folding/locale-specific logic ngoài `toLowerCase(Locale.ROOT)`.

**Policy:** Chỉ normalize theo một specification đã công bố; phải test Unicode inputs representative.

## 39. Chương trình chạy: Unicode NFC normalization

Tạo **`RecordUnicodeDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.Objects;

public class RecordUnicodeDemo {
    record Label(String value) {
        Label {
            value = Normalizer.normalize(
                    Objects.requireNonNull(value, "value"),
                    Normalizer.Form.NFC);
        }
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        Label a = new Label(composed);
        Label b = new Label(decomposed);

        System.out.println("same=" + a.equals(b));
        System.out.println("length=" + a.value().length());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordUnicodeDemo.java
java RecordUnicodeDemo
~~~

Stdout:

~~~text
same=true
length=1
~~~

Unicode NFC đưa hai representations về canonical form theo mục tiêu đã chọn. `String.length()` là UTF-16 code-unit count; ở normalized `é` ví dụ trên là 1.

## 40. Chuẩn hóa số và BigDecimal có quy tắc riêng

`BigDecimal.equals` quan tâm tới value **và scale**, nên:

~~~java
new java.math.BigDecimal("1.0")
    .equals(new java.math.BigDecimal("1.00"))
~~~

trả false, dù `compareTo` trả 0.

Nếu record coi hai amounts là cùng giá trị, cần domain canonicalization. Có thể dùng `stripTrailingZeros()` cho trường hợp phù hợp, hoặc chuẩn hóa bằng `setScale(n, roundingMode)` theo currency precision.

**Không tự làm tròn tiền mà không có contract**; rounding có thể ảnh hưởng giao dịch.

### Chương trình chạy

Tạo **`RecordBigDecimalDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class RecordBigDecimalDemo {
    record Amount(BigDecimal value) {
        Amount {
            value = Objects.requireNonNull(value, "value")
                    .stripTrailingZeros();

            if (value.signum() < 0) {
                throw new IllegalArgumentException("negative");
            }
        }
    }

    public static void main(String[] args) {
        Amount a = new Amount(new BigDecimal("1.0"));
        Amount b = new Amount(new BigDecimal("1.00"));

        System.out.println("equal=" + a.equals(b));
        System.out.println("value=" + a.value().toPlainString());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordBigDecimalDemo.java
java RecordBigDecimalDemo
~~~

Stdout:

~~~text
equal=true
value=1
~~~

`BigDecimal` immutable nên không cần clone. Normalization do business value-equivalence rule quyết định.

## 41. Legacy `java.util.Date` là mutable

Nếu record component là Date, input Date có thể bị sửa qua setter như `setTime`. Accessor mặc định cũng trả Date reference trực tiếp.

~~~java
record Event(java.util.Date when) {}
~~~

Đây không phải immutable snapshot.

Có hai hướng:
1. **Ưu tiên java.time**: dùng `Instant`, `LocalDate`, `LocalDateTime` hoặc `ZonedDateTime` theo domain; các types này immutable.
2. Nếu phải giữ Date theo legacy API, copy ở constructor và accessor.

## 42. Chương trình chạy: Date defensive copy

Tạo **`LegacyDateRecordDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

public class LegacyDateRecordDemo {
    record Event(Date when) {
        Event {
            when = new Date(
                    Objects.requireNonNull(when, "when").getTime());
        }

        @Override
        public Date when() {
            return new Date(when.getTime());
        }
    }

    public static void main(String[] args) {
        Date input = new Date(1000L);
        Event event = new Event(input);

        input.setTime(9000L);
        System.out.println("stored=" + event.when().getTime());

        Date output = event.when();
        output.setTime(5000L);
        System.out.println("after getter=" + event.when().getTime());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LegacyDateRecordDemo.java
java LegacyDateRecordDemo
~~~

Stdout:

~~~text
stored=1000
after getter=1000
~~~

Ví dụ có control qua timestamp, không phụ thuộc timezone default khi in Date.toString. Nếu có thể, `record Event(Instant when)` thường rõ và ít copy hơn.

## 43. Factory methods có thể thêm contract nhưng không thay canonical constructor

Record có thể có static factories:

~~~java
record Tag(String value) {
    Tag {
        value = value.strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank");
        }
    }

    static Tag fromUserInput(String raw) {
        return new Tag(raw);
    }
}
~~~

Factory giúp đặt tên use case, parse/convert input hoặc xử lý checked boundary. Nhưng nếu canonical constructor vẫn public/package-accessible, caller có thể bypass **logic chỉ nằm trong factory**.

**Nguyên tắc:** Invariants cốt lõi cần được bảo vệ ở canonical constructor, không chỉ ở một optional factory. Factories có thể thêm conversion steps, nhưng không được là cổng duy nhất giúp đối tượng hợp lệ nếu constructor cũng exposed.

## 44. Chương trình chạy: factory chuẩn hóa nguồn dữ liệu

Tạo **`RecordFactoryDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class RecordFactoryDemo {
    record CountryCode(String value) {
        CountryCode {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (!value.matches("[A-Z]{2}")) {
                throw new IllegalArgumentException("country code");
            }
        }

        static CountryCode fromInput(String raw) {
            return new CountryCode(raw);
        }
    }

    public static void main(String[] args) {
        CountryCode code = CountryCode.fromInput(" vn ");
        System.out.println(code.value());

        try {
            new CountryCode("Vietnam");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordFactoryDemo.java
java RecordFactoryDemo
~~~

Stdout:

~~~text
VN
invalid=country code
~~~

Dù caller dùng factory hay gọi constructor, validation/normalization vẫn được áp dụng.

## 45. Constructors phụ phải delegate về canonical constructor

Record có thể khai báo constructors bổ sung với signature khác, nhưng non-canonical constructors phải bắt đầu bằng **explicit constructor invocation** tới canonical constructor (thường thông qua `this(...)`). Không bỏ qua canonical validation.

~~~java
record Range(int start, int end) {
    Range {
        if (end < start) {
            throw new IllegalArgumentException("range");
        }
    }

    Range(int end) {
        this(0, end);
    }
}
~~~

Nhờ delegate, các invariants tại compact canonical constructor vẫn có hiệu lực cả với overload.

### Chương trình chạy

Tạo **`RecordConstructorDelegationDemo.java`**:

~~~java
public class RecordConstructorDelegationDemo {
    record Range(int start, int end) {
        Range {
            if (end < start) {
                throw new IllegalArgumentException("range");
            }
        }

        Range(int end) {
            this(0, end);
        }
    }

    public static void main(String[] args) {
        System.out.println(new Range(5));
        System.out.println(new Range(2, 7));

        try {
            new Range(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordConstructorDelegationDemo.java
java RecordConstructorDelegationDemo
~~~

Stdout:

~~~text
Range[start=0, end=5]
Range[start=2, end=7]
invalid=range
~~~

`new Range(-1)` delegate `this(0,-1)`, rồi canonical invariant ném exception.

## 46. Accessor tùy chỉnh và record API contract

Một record auto-generates accessor chỉ khi bạn không tự định nghĩa method cùng signature. Bạn có thể override component accessor:

~~~java
record Secret(byte[] payload) {
    Secret {
        payload = payload.clone();
    }

    @Override
    public byte[] payload() {
        return payload.clone();
    }
}
~~~

Accessor phải có **đúng return type và signature** theo record component contract và accessibility phù hợp.

Tuy nhiên hãy cân nhắc **semantic consistency**: record data state dùng trong equals/hashCode/toString được xác định theo record components và cơ chế generation, không mặc định áp dụng mọi transformation do custom accessor làm ra.

Một accessor trả defensive copy nên có *giá trị tương đương về nội dung* mỗi lần; tránh accessor có tác dụng phụ không đoán được hoặc sinh ra giá trị logic khác.

## 47. Record không cho thêm instance fields tùy ý

Record chỉ có instance fields từ declared components; bạn không thể thêm một instance field không thuộc components để “giữ bản backup” mà vẫn giữ record declaration hợp lệ.

~~~java
record Person(String name) {
    // private final String normalizedName; // Lỗi: extra instance field.
}
~~~

Records có thể có static fields phù hợp, nhưng static state không thay thế per-instance immutable components.

Nếu cần internal mutable caches, lazy state, locks, vòng đời resources hoặc representation không khớp components, **ordinary class** có thể phù hợp hơn.

## 48. Record invariants phải đúng với component accessors

Một nguyên tắc của record data-carrier design: tạo lại record từ component accessors nên cho một record equal theo contract với original, ví dụ:

~~~java
record Pair(int left, int right) {}

Pair p = new Pair(1, 2);
Pair copy = new Pair(p.left(), p.right());
System.out.println(p.equals(copy)); // true
~~~

Khi normalize, canonical constructor có thể đưa values về dạng chuẩn, nên property này vẫn giữ nếu accessor trả value đã lưu.

Với arrays và defensive copies, **default equality** theo array identity có thể làm `new Blob(blob.bytes())` không equal Blob gốc. Đó là lý do cần suy nghĩ kỹ về `equals/hashCode` theo nội dung.

### Tránh accessor phá hợp đồng

Nếu accessor tự tăng counter hoặc trả dữ liệu biến thiên khác với component state, record có thể không còn trực quan là một transparent carrier. Nếu logic đòi stateful access, cân nhắc class thường.

## 49. Chương trình chạy: reconstruction property sau normalize

Tạo **`RecordReconstructionDemo.java`**:

~~~java
import java.util.Locale;

public class RecordReconstructionDemo {
    record Code(String value) {
        Code {
            value = value.strip().toLowerCase(Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("empty");
            }
        }
    }

    public static void main(String[] args) {
        Code first = new Code("  AbC ");
        Code rebuilt = new Code(first.value());

        System.out.println("first=" + first.value());
        System.out.println("rebuilt=" + rebuilt.value());
        System.out.println("equal=" + first.equals(rebuilt));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordReconstructionDemo.java
java RecordReconstructionDemo
~~~

Stdout:

~~~text
first=abc
rebuilt=abc
equal=true
~~~

Normalization nên **idempotent**: chuẩn hóa một giá trị đã chuẩn không đổi nó về mặt logical state.

## 50. Mutable object với custom `equals/hashCode` cũng có thể nguy hiểm

Không chỉ arrays: một component có custom mutable state và equals/hashCode dựa trên state có thể làm record hash thay đổi sau construction.

~~~java
record Wrapper(MutablePrice price) {}
~~~

Nếu MutablePrice hashCode đổi khi amount đổi, record Wrapper.hashCode cũng có thể đổi. Dù component field final, hash-based collection contract có thể bị phá.

Các options:
- thay mutable component bằng immutable value record;
- sao chép state sang immutable domain representation;
- chỉ định custom equals/hashCode khi thực sự cần, với stable values;
- tránh dùng mutable-record-wrapper làm Map key.

Defensive copy là giải pháp về **reference ownership**, còn correct equality/hash là vấn đề **value semantics** có liên quan mật thiết nhưng không hoàn toàn đồng nhất.

## 51. Tính đúng đắn khi input collection bị sửa đồng thời

`List.copyOf(source)` đọc elements của source tại thời điểm gọi, nhưng nếu thread khác mutate một non-thread-safe mutable collection đồng thời, kết quả có thể thiếu nhất quán hoặc phát sinh exception; `List.copyOf` không phải atomic transaction snapshot cho arbitrary concurrent sources.

Nếu cần snapshot của shared concurrent state:
- thiết lập synchronization/lock quanh snapshot theo ownership policy;
- hoặc dùng data structures/publishing mechanism có consistency contract rõ;
- hoặc truyền immutable snapshot do producer tạo;
- không giả định `copyOf` bảo đảm một “instant” nguyên tử cho mọi collection.

Cơ chế nào thích hợp phụ thuộc yêu cầu consistency và concurrency design, không chỉ syntax record.

## 52. Validation nên kiểm tra nội dung hay chỉ non-null?

Ví dụ:

~~~java
record Catalog(java.util.List<String> codes) {
    Catalog {
        codes = java.util.List.copyOf(codes);
    }
}
~~~

`List.copyOf` kiểm tra null list và null elements, nhưng **không** kiểm tra:
- chuỗi blank;
- duplicate code;
- độ dài tối đa;
- format regex;
- quan hệ giữa codes và các components khác.

Nếu domain yêu cầu, thêm checks rõ ràng, tốt nhất validate một lần rồi copy:

~~~java
for (String code : codes) {
    if (code.isBlank()) {
        throw new IllegalArgumentException("blank code");
    }
}
codes = List.copyOf(codes);
~~~

Với concurrent modification potential, nên copy snapshot **trước**, sau đó validate snapshot ổn định nếu input có thể bị sửa ngoài ý muốn. Validation/copy order phải bảo đảm checks áp dụng cho **chính dữ liệu được lưu**.

## 53. Chương trình chạy: validate snapshot collection

Tạo **`RecordListValidationDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class RecordListValidationDemo {
    record Catalog(List<String> codes) {
        Catalog {
            codes = List.copyOf(
                    Objects.requireNonNull(codes, "codes"));

            for (String code : codes) {
                if (code.isBlank()) {
                    throw new IllegalArgumentException("blank code");
                }
            }

            if (codes.isEmpty()) {
                throw new IllegalArgumentException("empty catalog");
            }
        }
    }

    public static void main(String[] args) {
        Catalog catalog = new Catalog(List.of("A", "B"));
        System.out.println("codes=" + catalog.codes());

        try {
            new Catalog(List.of("A", " "));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordListValidationDemo.java
java RecordListValidationDemo
~~~

Stdout:

~~~text
codes=[A, B]
invalid=blank code
~~~

Code copy structure trước, sau đó validate đúng snapshot sẽ được lưu.

## 54. Duplicates và canonicalization của collections

Nếu domain coi input collection là *set of unique normalized tags*, một record `List<String>` có thể chuẩn hóa:
1. copy source;
2. map strings sang normalized tags;
3. reject blank/invalid;
4. deduplicate theo quy tắc;
5. lưu List unmodifiable với thứ tự xác định.

Nhưng deduplication có thể **âm thầm làm mất thông tin**; không nên tự làm nếu không có domain requirement.

Nếu giữ insertion order sau khi loại duplicates, có thể dùng `LinkedHashSet` trong normalization rồi `List.copyOf`; nếu dùng `Set.copyOf`, không có ordering guarantee.

## 55. Chương trình chạy: normalized unique tags

Tạo **`RecordNormalizedTagsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class RecordNormalizedTagsDemo {
    record Tags(List<String> values) {
        Tags {
            Objects.requireNonNull(values, "values");
            LinkedHashSet<String> unique = new LinkedHashSet<>();

            for (String raw : values) {
                String tag = Objects.requireNonNull(raw, "tag")
                        .strip()
                        .toLowerCase(Locale.ROOT);

                if (tag.isEmpty()) {
                    throw new IllegalArgumentException("blank tag");
                }

                unique.add(tag);
            }

            values = List.copyOf(new ArrayList<>(unique));
        }
    }

    public static void main(String[] args) {
        Tags tags = new Tags(
                List.of(" Java ", "CORE", "java", "Core"));

        System.out.println(tags.values());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordNormalizedTagsDemo.java
java RecordNormalizedTagsDemo
~~~

Stdout:

~~~text
[java, core]
~~~

Domain policy này coi tag names case-insensitive và giữ first-seen order. Với domain case-sensitive, **không** lower-case.

## 56. Record nhận input ngoài: parse ở boundary, validate trong record

Ví dụ DTO từ HTTP/CLI/config có thể tới dưới dạng Strings. Nên tách:
- **Parsing**: `String` → `int`, `LocalDate`, `BigDecimal`;
- **Construction & invariant**: record canonical constructor bảo vệ domain state;
- **Error reporting**: boundary chuyển exception thành message phù hợp cho user.

~~~java
record Port(int number) {
    Port {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("port out of range");
        }
    }

    static Port parse(String raw) {
        return new Port(Integer.parseInt(raw.strip()));
    }
}
~~~

Nếu raw không phải number, `NumberFormatException` từ parsing; nếu là number ngoài range, IllegalArgumentException từ domain constructor. Hai stages có mục đích khác.

## 57. Chương trình chạy: parse và validate tách biệt

Tạo **`RecordParsingDemo.java`**:

~~~java
public class RecordParsingDemo {
    record Port(int number) {
        Port {
            if (number < 1 || number > 65535) {
                throw new IllegalArgumentException("port out of range");
            }
        }

        static Port parse(String raw) {
            return new Port(Integer.parseInt(raw.strip()));
        }
    }

    public static void main(String[] args) {
        System.out.println("valid=" + Port.parse(" 8080 ").number());

        try {
            Port.parse("70000");
        } catch (IllegalArgumentException ex) {
            System.out.println("domain=" + ex.getMessage());
        }

        try {
            Port.parse("invalid");
        } catch (NumberFormatException ex) {
            System.out.println("parse rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordParsingDemo.java
java RecordParsingDemo
~~~

Stdout:

~~~text
valid=8080
domain=port out of range
parse rejected
~~~

`NumberFormatException` extends IllegalArgumentException, nên đặt catch của NumberFormatException riêng trong scope phù hợp nếu cần phân biệt từ exception hierarchy.

## 58. Record và validation annotations

Các Java frameworks có thể hỗ trợ Jakarta Bean Validation annotations (`@NotNull`, `@Size`, v.v.) trên record components/constructor parameters/accessors, nhưng **annotation tự nó không đảm bảo constructor được validate ở mọi `new Record(...)`**. Cần framework/invocation mechanism phù hợp.

Nếu invariant phải đúng với **mọi caller**, ghi checks trong canonical constructor là cách rõ ràng, độc lập frameworks.

Validation annotations có thể hữu ích cho DTO boundary với error aggregation, nhưng core domain record vẫn cần contract mà code thực sự thực thi.

## 59. Khi nào không nên dùng record?

Record rất phù hợp nếu state đúng bằng một tập components có value-oriented semantics. Cân nhắc class thường khi:

- Object có identity/lifecycle hơn là value semantics.
- Cần mutable internal state phức tạp hoặc lazy caches.
- Cần giữ resource handle (socket/thread/session) có ownership/close lifecycle đặc biệt.
- Cần superclass tùy ý.
- Cần nhiều constructors với representation không phù hợp canonical components.
- Cần encapsulation ẩn hoàn toàn representation, không muốn component accessors.
- Defensive-copy logic trở nên quá phức tạp hoặc performance contract quá khác record semantics.

Một record có array component và deep equality override vẫn hợp lệ; nhưng nếu phải viết quá nhiều custom logic, class immutable có tên và API rõ có thể dễ bảo trì hơn.

## 60. Các anti-patterns phổ biến

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tin record auto-validates inputs | null/negative/blank lọt vào | Canonical validation |
| Nghĩ field `final` làm List immutable | Caller sửa List | `List.copyOf`/snapshot |
| Bọc mutable List trực tiếp bằng `unmodifiableList` | Source vẫn sửa underlying collection | Copy trước khi wrap |
| Dùng `List.copyOf` rồi tuyên bố deep copy | Elements mutable vẫn đổi | Immutable elements/deep snapshot |
| Clone array chỉ trong constructor | Getter lộ array nội bộ | Override accessor clone |
| Clone getter nhưng quên constructor | Input alias sửa record | Clone cả hai hướng |
| Clone arrays nhưng dựa default equals cho content | Same bytes nhưng unequal | Override equals/hashCode nếu value semantics |
| Dùng `getClass()==Record.class` với nested subclass assumption | Sai abstraction | Dựa record type/contract |
| Gán `this.component=...` trong compact constructor | Compile error | Gán parameter |
| Chỉ validate trong static factory | Direct constructor bypass | Validate canonical constructor |
| Dùng `assert` cho validation | Assertions có thể bị disable | Throw exception bình thường |
| Lower-case/strip mọi string | Thay đổi domain meaning | Policy explicit |
| Dùng default locale cho identifier | Behavior phụ thuộc môi trường | Locale.ROOT khi technical identifier |
| Không phân biệt input normalization và validation | Chấp nhận/từ chối sai | Specify contract rõ |
| Dùng mutable record key trong HashMap | Hash/equality biến đổi | Immutable snapshot |
| Dùng `Stream.toList` rồi giả định cấm null | Null có thể lọt | Validation/List.copyOf nếu yêu cầu |
| Dùng `Set.copyOf` và kỳ vọng giữ order | Không có ordering guarantee | List/ordered snapshot contract |
| Dùng mutable Date trực tiếp | External mutation | Instant hoặc copy constructor+accessor |
| Snapshot source đang bị sửa đồng thời không lock | Inconsistent data | Synchronization/immutable snapshot |
| Parse/IO phức tạp trong canonical constructor | Coupling, side effects | Factory/boundary tách riêng |

## 61. Bài tập 1 — Compact constructor có được viết như sau?

~~~java
record Username(String text) {
    Username {
        // this.text = text.strip();
    }
}
~~~

**Đáp án:** Không nếu uncomment assignment tới component field `this.text` trong compact constructor. Viết `text = text.strip();` và compiler gán field tự động sau body.

## 62. Bài tập 2 — Null policy

~~~java
record Name(String value) {
    Name {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
    }
}
~~~

**Đáp án:** Input null → NullPointerException("value"); input `"   "` → IllegalArgumentException("empty"); input `" A "` → lưu `"A"`.

## 63. Bài tập 3 — List.copyOf có sâu không?

Input `List<MutableItem>`, record constructor dùng `List.copyOf`. Sau đó caller thay field trên một MutableItem được tham chiếu từ list.

**Đáp án:** Record vẫn có thể quan sát item mới vì `List.copyOf` chỉ copy snapshot cấu trúc list, không deep copy elements. Cần immutable elements hoặc map mỗi element sang immutable snapshot.

## 64. Bài tập 4 — Hai hướng array

Record Blob copy array ở constructor nhưng để accessor mặc định `bytes()`.

**Đáp án:** Caller có thể gọi `blob.bytes()[0]=99` và thay internal array. Override accessor để return clone.

## 65. Bài tập 5 — Arrays và equality

Hai record `Blob(byte[] bytes)` đều giữ new byte[] {1,2}. Generated equals có chắc true không?

**Đáp án:** Không, array components mặc định được so sánh theo reference identity, không theo content. Muốn content equality, override equals/hashCode dùng Arrays methods phù hợp.

## 66. Bài tập 6 — List live view

~~~java
List<String> source = new ArrayList<>();
List<String> view = Collections.unmodifiableList(source);
source.add("A");
~~~

**Đáp án:** `view` sẽ thấy A vì unmodifiable wrapper không snapshot source. `List.copyOf(source)` hoặc `unmodifiableList(new ArrayList<>(source))` mới snapshot cấu trúc ở thời điểm copy.

## 67. Bài tập 7 — String normalization

Hai Username được tạo từ `"  AbC  "` và `"abc"`. Compact constructor dùng strip và toLowerCase(Locale.ROOT). Hai records equals thế nào?

**Đáp án:** True nếu components khác đều giống nhau. Both store canonical `"abc"`; generated String component equality phản ánh normalized value.

## 68. Bài tập 8 — Map.copyOf

Có thể lưu `Map<String,MutableValue>` bằng Map.copyOf và gọi object deep immutable được không?

**Đáp án:** Không. Map entries structure unmodifiable, nhưng MutableValue objects vẫn được chia sẻ; phải snapshot values nếu deep immutability cần thiết.

## 69. Bài tập 9 — Record key trong HashMap

Record Key chứa mutable List không copy. Sau khi insert key, caller thêm element vào List. Rủi ro?

**Đáp án:** Key.hashCode có thể đổi, HashMap lookup không còn ổn định. Copy sang immutable list trong constructor và bảo đảm elements themselves immutable.

## 70. Bài tập 10 — Date hay Instant?

Một event timestamp không cần mutate và phải lưu snapshot.

**Đáp án:** Ưu tiên java.time.Instant immutable. Nếu legacy API bắt buộc java.util.Date, copy Date lúc constructor và mỗi accessor call; không chỉ final Date field.

## 71. Bài tập 11 — Auxiliary constructor

Record Range có canonical constructor validate start <= end. Constructor overload `Range(int end)` được phép tự gán fields thay vì delegate không?

**Đáp án:** Không; non-canonical constructor phải delegate bằng `this(...)` phù hợp tới một constructor của record, cuối cùng đi qua canonical initialization. Ví dụ `Range(int end) { this(0,end); }`.

## 72. Bài tập 12 — Chọn record hay class

Một object cần mutable internal cache, lifecycle close và resource ownership, có nhiều invariants không biểu diễn bằng transparent components.

**Đáp án:** Cân nhắc ordinary class với explicit private state, constructors, methods và close policy. Record chỉ nên dùng nếu value-carrier semantics thực sự phù hợp.

## 73. Quy trình thiết kế một record an toàn

**Bước 1 — Liệt kê components.** Phân loại mỗi component là primitive, immutable object, mutable collection/array hoặc nested object graph.

**Bước 2 — Viết invariants.** Null, blank, range, cross-field constraints, uniqueness và độ dài.

**Bước 3 — Quy định normalization.** Trim/strip, case, Unicode, BigDecimal scale, ordering/dedup — chỉ khi domain yêu cầu.

**Bước 4 — Chọn canonical constructor.** Compact cho validation/parameter reassignment; explicit nếu có lý do rõ.

**Bước 5 — Lưu snapshot.** List/Set/Map copyOf với null/order policy; clone arrays; deep-copy elements nếu mutable.

**Bước 6 — Kiểm tra accessor.** Array/Date cần defensive copy khi trả ra; unmodifiable List of immutable elements thường không cần copy lại getter.

**Bước 7 — Kiểm tra generated equals/hashCode/toString.** Array content equality cần custom methods nếu value semantics. Tránh exposing credentials qua toString.

**Bước 8 — Kiểm tra constructors/factories bổ sung.** Không cho bypass invariants.

**Bước 9 — Viết negative tests.** Null, blank, out-of-range, duplicate, invalid formats.

**Bước 10 — Viết aliasing tests.** Mutate input sau construction, mutate getter output, mutate nested element references.

**Bước 11 — Viết equality/hash tests.** Equivalent normalized inputs, HashMap lookup, reconstruction property.

**Bước 12 — Review concurrency/ownership.** Input shared with other threads? Có lifecycle/resource state hay không?

## 74. Checklist cuối bài

- [ ] Tôi biết record auto-generates components nhưng không auto-validates.
- [ ] Tôi phân biệt validation và normalization.
- [ ] Tôi biết compact constructor dùng parameter names và implicit assignments.
- [ ] Tôi không gán trực tiếp `this.component` trong compact constructor.
- [ ] Tôi biết explicit canonical constructor phải gán component fields.
- [ ] Tôi validate null/blank/range và cross-component invariants.
- [ ] Tôi biết normalization phải dựa domain rules.
- [ ] Tôi dùng Locale.ROOT đúng chỗ cho technical identifiers.
- [ ] Tôi phân biệt null exceptions và invalid-domain exceptions.
- [ ] Tôi không dùng assert thay real validation.
- [ ] Tôi dùng List.copyOf để snapshot cấu trúc list.
- [ ] Tôi biết List.copyOf cấm null elements.
- [ ] Tôi biết List.copyOf có thể reuse unmodifiable input list.
- [ ] Tôi phân biệt unmodifiable view và copied snapshot.
- [ ] Tôi biết Set.copyOf/Map.copyOf không đảm bảo insertion order.
- [ ] Tôi phân biệt shallow copy và deep copy.
- [ ] Tôi snapshot mutable elements khi cần deep immutability.
- [ ] Tôi biết nested record vẫn có thể chứa mutable data.
- [ ] Tôi clone arrays ở constructor và accessor.
- [ ] Tôi biết array component default equals không element-wise.
- [ ] Tôi override equals/hashCode nhất quán cho byte[] value semantics.
- [ ] Tôi không dùng mutable record key trong HashMap.
- [ ] Tôi ưu tiên immutable java.time types khi phù hợp.
- [ ] Tôi defensive-copy legacy Date nếu phải dùng.
- [ ] Tôi biết BigDecimal equals phụ thuộc scale.
- [ ] Tôi hiểu factory không thay canonical validation.
- [ ] Tôi biết auxiliary constructor phải delegate.
- [ ] Tôi kiểm tra reconstruction property với normalized inputs.
- [ ] Tôi biết concurrent mutation cần synchronization policy.
- [ ] Tôi test aliasing cả input và accessor output.
- [ ] Tôi không đưa secret vào record toString khi phải bảo mật.
- [ ] Tôi biết khi nào ordinary class phù hợp hơn record.

**Kết luận:** Record trong Java 17 chỉ cung cấp **cấu trúc value-carrier và các operations được sinh ra từ components**; tính đúng đắn và bất biến sâu vẫn thuộc trách nhiệm thiết kế. Hãy **validate và normalize trong canonical constructor**, dùng **List.copyOf/Map.copyOf** cho immutable structural snapshots, **deep-copy mutable elements khi cần**, và **clone arrays ở cả constructor lẫn accessor**. Sau đó kiểm tra `equals/hashCode/toString`, nhất là với arrays và mutable components, để record thực sự đáp ứng value semantics và an toàn khi được dùng làm key hoặc chia sẻ giữa các phần của chương trình.
