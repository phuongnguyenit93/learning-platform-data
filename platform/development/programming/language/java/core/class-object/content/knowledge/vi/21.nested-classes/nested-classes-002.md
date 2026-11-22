# Static nested class không cần đối tượng bao ngoài trong Java

Trong Java, một **static nested class** là một lớp thành viên được khai báo **bên trong một lớp hoặc interface khác**, với modifier `static` khi thích hợp. Điểm mấu chốt: **mỗi instance của static nested class không tự mang tham chiếu ngầm định tới một instance của lớp bao ngoài**. Vì vậy có thể viết `new Outer.Nested()` mà **không cần** tạo `new Outer()` trước.

~~~java
class Outer {
    static class Nested {
        String message() {
            return "Hello from Nested";
        }
    }
}
~~~

Đây là định nghĩa lớp minh họa hợp lệ. Nếu `Nested` được phép truy cập từ vị trí gọi, ta tạo object bằng `Outer.Nested object = new Outer.Nested();`. Lớp `Nested` **không phải object static**: mỗi lần `new Outer.Nested()` vẫn tạo một object có identity, instance fields và instance methods riêng.

Bài thuộc **Java core - class-object**, mục **Lớp lồng nhau**. Trọng tâm là mối quan hệ **static nested class – enclosing class – inner class** trong Java 17+: cú pháp, đối tượng bao ngoài, quy tắc truy cập, `Outer.this`, type parameters, constructors, scope, initialization, bytecode, khi nào nên dùng và lỗi thường gặp. Các chương trình hoàn chỉnh có tên tệp, lệnh biên dịch/chạy và **stdout xác định**.

## 1. Thuật ngữ: nested class, member class và inner class

Một **nested class** được khai báo bên trong phạm vi một lớp hoặc interface. Trong bài này, ta chủ yếu phân biệt hai dạng **member class**:

- **Static nested class:** khai báo `static class Nested` trong class bao ngoài; không có enclosing instance ngầm định.
- **Non-static member class**, thường gọi **inner class:** khai báo `class Inner` bên trong class bao ngoài (không có modifier `static`); mỗi instance được gắn với một enclosing instance thích hợp.

Ngoài ra Java còn có **local classes** (khai báo trong block) và **anonymous classes** (tạo ngay qua biểu thức), nhưng chúng có những quy tắc riêng. Không nên gọi tất cả các lớp bên trong là “inner class” theo nghĩa kỹ thuật của Java Language Specification.

| Đặc điểm | Static nested class | Non-static inner member class |
| --- | --- | --- |
| Cách khai báo trong một outer class | `static class Nested` | `class Inner` |
| Cần instance của Outer khi tạo? | **Không** | Thường **có** |
| Cú pháp thông dụng | `new Outer.Nested()` | `outer.new Inner()` |
| Tự có reference `Outer.this`? | **Không** | Có enclosing instance phù hợp |
| Truy cập instance field của Outer không có reference? | Không | Có thể qua enclosing instance |
| Truy cập static field của Outer? | Có theo quy tắc access/scope | Có theo quy tắc access/scope |
| Có instance fields/methods riêng? | Có | Có |
| Có constructors riêng? | Có | Có |
| Có thể mang type parameters riêng? | Có | Có |

**Học đúng hai tầng:** `static` ở đây mô tả **quan hệ lớp lồng với lớp bao**, không có nghĩa instance của Nested là singleton, không có nghĩa mọi method của Nested đều phải `static`, và không có nghĩa compiler tạo object Outer tự động.

## 2. Chương trình hoàn chỉnh 1 — tạo nested object khi chưa tạo Outer

Tạo tệp **`StaticNestedBasicsDemo.java`**:

~~~java
class School {
    private static final String PREFIX = "Course";

    static class CourseCode {
        private final String code;

        CourseCode(String code) {
            this.code = code;
        }

        String display() {
            return PREFIX + ":" + code;
        }
    }

    private final String schoolName;

    School(String schoolName) {
        this.schoolName = schoolName;
        System.out.println("School constructor: " + schoolName);
    }

    String name() {
        return schoolName;
    }
}

public class StaticNestedBasicsDemo {
    public static void main(String[] args) {
        School.CourseCode first =
                new School.CourseCode("J17");
        School.CourseCode second =
                new School.CourseCode("OOP");

        System.out.println("first=" + first.display());
        System.out.println("second=" + second.display());
        System.out.println("different=" + (first != second));

        School school = new School("North");
        System.out.println("outer=" + school.name());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StaticNestedBasicsDemo.java
java StaticNestedBasicsDemo
~~~

**Stdout chính xác:**

~~~text
first=Course:J17
second=Course:OOP
different=true
School constructor: North
outer=North
~~~

**Giải thích:**

1. Hai lời gọi `new School.CourseCode(...)` chạy **constructors của CourseCode**. Chúng không chạy constructor `School(String)`.
2. `School` mới được tạo khi thực hiện riêng `new School("North")`, sau hai dòng đầu ra về course codes.
3. `CourseCode` truy cập `School.PREFIX` vì `PREFIX` là static field và quy tắc access cho phép.
4. Hai course codes là **hai objects khác nhau** dù class của chúng được khai báo static nested.
5. Field `schoolName` là instance field của School; static nested class không được tự ý viết `return schoolName;` khi không có reference `School`.

`PREFIX` là static final String constant. Việc dùng nó không tạo ra enclosing instance nào.

## 3. Cú pháp khai báo và cú pháp sử dụng

Dạng cơ bản:

~~~java
class Container {
    public static class Item {
        public Item() {
        }

        public String kind() {
            return "item";
        }
    }
}
~~~

Đây là mã minh họa hợp lệ, gồm hai classes; `Item` được khai báo `public static` để code có quyền truy cập có thể gọi:

~~~java
Container.Item item = new Container.Item();
String result = item.kind();
~~~

Điều cần phân biệt:

- `Container.Item` là **tên kiểu được qualified** bởi tên class bao ngoài.
- `new Container.Item()` là **biểu thức tạo instance của Item**.
- `Container.Item` **không phải field tên Item** của một object Container.
- `new Container().new Item()` **không phải cú pháp dành cho static nested class**; đó là kiểu cú pháp tạo non-static inner object.
- Nếu `Item` chỉ package-private, code ở package khác không thể truy cập nó tùy tiện; nếu `private`, chỉ code có quyền theo nesting/access rules mới dùng được.

Lớp bao có thể có các constructors riêng, nhưng constructor của static nested class **không tự nhận một tham số Outer ngầm định**. Nếu cần dữ liệu từ một object Outer, hãy truyền dữ liệu hoặc reference vào constructor Nested một cách **tường minh**.

## 4. Class nested là “static”, object bên trong vẫn có trạng thái instance

Không nên nghĩ: “`static class` nên dữ liệu của tất cả nested objects phải dùng chung.”

~~~java
class CounterBox {
    static class Counter {
        private int count;

        void increase() {
            count++;
        }

        int value() {
            return count;
        }
    }
}
~~~

Đây là định nghĩa hợp lệ. `count` là **instance field của Counter**: mỗi `new CounterBox.Counter()` có giá trị `count` riêng.

Lớp Counter cũng có thể khai báo static field riêng:

~~~java
class Box {
    static class Counter {
        private static int created;

        Counter() {
            created++;
        }

        static int createdCount() {
            return created;
        }
    }
}
~~~

Trong định nghĩa minh họa thứ hai, `created` là static field **của Counter**, nên được chia sẻ bởi tất cả Counter instances thuộc cùng runtime class. Modifier `static` ở class declaration và modifier `static` ở field declaration là **hai quyết định khác nhau**.

## 5. Chương trình hoàn chỉnh 2 — instance state và static state của nested class

Tạo tệp **`NestedStateDemo.java`**:

~~~java
class Game {
    static class Score {
        private static int constructed;
        private int points;

        Score(int points) {
            this.points = points;
            constructed++;
        }

        void add(int amount) {
            points += amount;
        }

        int points() {
            return points;
        }

        static int constructed() {
            return constructed;
        }
    }
}

public class NestedStateDemo {
    public static void main(String[] args) {
        Game.Score a = new Game.Score(10);
        Game.Score b = new Game.Score(20);

        a.add(5);
        System.out.println("a=" + a.points());
        System.out.println("b=" + b.points());
        System.out.println("same=" + (a == b));
        System.out.println("created="
                + Game.Score.constructed());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 NestedStateDemo.java
java NestedStateDemo
~~~

**Stdout:**

~~~text
a=15
b=20
same=false
created=2
~~~

Hai `Score` objects giữ điểm khác nhau vì `points` là instance field. Nhưng counter `constructed` là static field thuộc `Game.Score`; hai constructions tăng cùng một biến.

**Lưu ý concurrency:** nếu nhiều threads cùng tăng `constructed++`, phép tăng này không tự atomic chỉ vì field nằm trong static nested class. Muốn đếm chính xác dưới tranh chấp phải dùng cơ chế như `AtomicInteger` hoặc synchronization phù hợp.

## 6. So sánh chính xác với non-static inner class

Một non-static inner member class cần **enclosing instance**. Nó có thể tham chiếu instance state của Outer mà không cần truyền một object Outer qua constructor tường minh.

Tạo tệp **`StaticVsInnerDemo.java`**:

~~~java
class Library {
    private final String branch;
    private static final String SYSTEM = "Catalog";

    Library(String branch) {
        this.branch = branch;
        System.out.println("Library created: " + branch);
    }

    class Shelf {
        String describe() {
            return branch + " / " + SYSTEM;
        }
    }

    static class BookCode {
        private final String code;

        BookCode(String code) {
            this.code = code;
        }

        String describe() {
            return SYSTEM + ":" + code;
        }
    }
}

public class StaticVsInnerDemo {
    public static void main(String[] args) {
        Library.BookCode code =
                new Library.BookCode("B1");
        System.out.println("nested=" + code.describe());

        Library library = new Library("West");
        Library.Shelf shelf = library.new Shelf();
        System.out.println("inner=" + shelf.describe());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticVsInnerDemo.java
java StaticVsInnerDemo
~~~

**Stdout chính xác:**

~~~text
nested=Catalog:B1
Library created: West
inner=West / Catalog
~~~

Trong ví dụ:

- `Library.BookCode` là **static nested class**. `BookCode` đọc được `SYSTEM`, nhưng không có reference ngầm tới một Library cụ thể để đọc `branch`.
- `Library.Shelf` là **non-static inner class**. `library.new Shelf()` gắn Shelf vừa tạo với `library`, vì vậy `Shelf.describe()` đọc `branch` của Library ấy.
- `new Library.BookCode("B1")` xảy ra **trước** khi tạo `library`; nó không làm constructor Library chạy.

Câu hỏi để tự kiểm tra: một helper object cần biết **chi nhánh thư viện cụ thể** hay chỉ cần định dạng code chung? Nếu chỉ làm việc với code chung, dùng static nested class thường đơn giản hơn.

## 7. Không có `Outer.this` trong static nested class

Ở một non-static inner class, `Outer.this` chỉ tới enclosing Outer instance thích hợp. Trong static nested class, **không có enclosing instance tự động**, nên cú pháp ấy không hợp lệ.

Ví dụ **cố ý không biên dịch nếu bỏ chú thích**:

~~~java
class Station {
    private final String name = "A";

    static class StaticMember {
        // String show() { return Station.this.name; }
        // Lỗi: không có enclosing instance Station.
    }

    class InnerMember {
        String show() {
            return Station.this.name;
        }
    }
}
~~~

Các dòng có chú thích mô tả tình huống lỗi compile-time; phần class còn lại là định nghĩa Java hợp lệ.

Tương tự, **không thể** trong static nested class viết:

~~~java
// return name;
~~~

nếu `name` chỉ là instance field của `Station` và không có biến nào trỏ tới một Station object. Không phải vì field `private` mới không truy cập được: vấn đề nằm ở **thiếu object receiver**. Ngay cả khi `name` là `public`, static nested class vẫn cần instance cụ thể để lấy giá trị instance field ấy.

## 8. Truy cập thành viên `private` của outer: được, nhưng cần đúng receiver

Static nested class thường được dùng làm chi tiết triển khai bên trong Outer. Vì cả hai thuộc cùng quan hệ nesting, Java cho phép truy cập nhiều private members qua quy tắc access thích hợp.

Phân biệt hai tình huống:

**Static member của outer:**

~~~java
class Vault {
    private static final int MAX = 100;

    static class Entry {
        int maximum() {
            return MAX;
        }
    }
}
~~~

`Entry.maximum()` đọc `Vault.MAX` trực tiếp, không cần Vault object.

**Instance member của outer:**

~~~java
class Vault {
    private final int secret;

    Vault(int secret) {
        this.secret = secret;
    }

    static class Inspector {
        int inspect(Vault target) {
            return target.secret;
        }
    }
}
~~~

Đây là một định nghĩa minh họa riêng (đừng ghép với class Vault trùng tên ở đoạn trước). `Inspector` **được phép đọc private field `secret`**, nhưng cần một **reference target** do caller cung cấp.

Hai câu trên không mâu thuẫn: **access control** trả lời “có quyền đọc field không?”, còn **instance ownership** trả lời “đọc field của object nào?”.

## 9. Chương trình hoàn chỉnh 3 — đọc private instance field qua tham số tường minh

Tạo tệp **`NestedAccessDemo.java`**:

~~~java
final class Account {
    private static final String TYPE = "BASIC";
    private final String owner;
    private final int balance;

    Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
    }

    private String secretSummary() {
        return owner + ":" + balance;
    }

    static class AuditView {
        String describe(Account target) {
            return TYPE + "/" + target.secretSummary();
        }

        int balanceOf(Account target) {
            return target.balance;
        }
    }
}

public class NestedAccessDemo {
    public static void main(String[] args) {
        Account.AuditView audit = new Account.AuditView();
        Account first = new Account("An", 50);
        Account second = new Account("Binh", 80);

        System.out.println("first=" + audit.describe(first));
        System.out.println("second=" + audit.describe(second));
        System.out.println("first balance="
                + audit.balanceOf(first));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NestedAccessDemo.java
java NestedAccessDemo
~~~

**Stdout:**

~~~text
first=BASIC/An:50
second=BASIC/Binh:80
first balance=50
~~~

`AuditView` không được tự động gắn với `first` hay `second`. Nó nhận Account qua tham số, nên có thể kiểm tra nhiều Account objects khác nhau, nhưng chỉ khi caller cung cấp chúng.

Vì `AuditView` là nested class của `Account`, code bên trong có thể truy cập private `secretSummary()` và private `balance` theo quy tắc Java. **Điều này không có nghĩa** bất cứ class độc lập nào ở ngoài cũng có cùng quyền private access.

**Cảnh báo thiết kế:** quyền private access là công cụ tổ chức implementation, không tự biến việc xuất bản thông tin nhạy cảm qua `AuditView.describe()` thành an toàn. Cần đặt access modifiers cho các API và kiểm soát dữ liệu theo yêu cầu thực tế.

## 10. Có thể truyền Outer reference vào static nested object nếu thật sự cần

Static nested class không có **tham chiếu Outer ngầm định**, nhưng bạn **có thể khai báo một field rõ ràng** trỏ tới Outer khi domain yêu cầu.

~~~java
class Workbench {
    private int completed;

    void finishOne() {
        completed++;
    }

    static class Button {
        private final Workbench target;

        Button(Workbench target) {
            this.target = java.util.Objects.requireNonNull(target);
        }

        void press() {
            target.finishOne();
        }
    }
}
~~~

Đây là class minh họa hợp lệ; `Workbench.Button` có reference `target` **vì chính lập trình viên khai báo**. Nó không phải hidden `Workbench.this` do compiler tự sinh như với non-static inner class.

Cấu trúc này phù hợp khi một đối tượng **có chủ đích** giữ dependency đến Workbench. Nếu Button chỉ cần một primitive code hay một immutable value, hãy truyền chính dữ liệu cần dùng thay vì luôn giữ cả outer object.

Điểm lợi của static nesting: **không bị buộc phải gắn với enclosing instance**. Bạn kiểm soát rõ có lưu Outer reference hay không.

## 11. Chương trình hoàn chỉnh 4 — dependency được truyền tường minh

Tạo tệp **`ExplicitOuterReferenceDemo.java`**:

~~~java
import java.util.Objects;

final class Machine {
    private final String name;
    private int jobsDone;

    Machine(String name) {
        this.name = name;
    }

    private void runJob() {
        jobsDone++;
    }

    int jobsDone() {
        return jobsDone;
    }

    static class Command {
        private final Machine machine;

        Command(Machine machine) {
            this.machine = Objects.requireNonNull(machine);
        }

        void execute() {
            machine.runJob();
        }

        String targetName() {
            return machine.name;
        }
    }
}

public class ExplicitOuterReferenceDemo {
    public static void main(String[] args) {
        Machine one = new Machine("M1");
        Machine two = new Machine("M2");
        Machine.Command first = new Machine.Command(one);
        Machine.Command second = new Machine.Command(two);

        first.execute();
        first.execute();
        second.execute();

        System.out.println("first target=" + first.targetName());
        System.out.println("second target=" + second.targetName());
        System.out.println("one jobs=" + one.jobsDone());
        System.out.println("two jobs=" + two.jobsDone());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ExplicitOuterReferenceDemo.java
java ExplicitOuterReferenceDemo
~~~

**Stdout:**

~~~text
first target=M1
second target=M2
one jobs=2
two jobs=1
~~~

`Machine.Command` được tạo bằng `new Machine.Command(one)`; **không cần** dùng `one.new Command()`, vì Command là static nested class.

Trong trường hợp này mỗi Command **chủ động lưu Machine reference**: điều đó có thể làm Machine được giữ sống trong heap chừng nào Command còn reachable. Không nên suy luận “static nested class không bao giờ giữ được Outer”: nó **chỉ không tự có hidden enclosing-instance reference**.

## 12. Kế thừa và quyền truy cập của static nested class

Một class lồng có thể mang access modifiers thích hợp như `public`, `protected`, package-private hoặc `private` khi khai báo là member class.

~~~java
public class ProductCatalog {
    public static class Entry {
        public String code() {
            return "P1";
        }
    }

    private static class Parser {
        static int parseId(String value) {
            return Integer.parseInt(value);
        }
    }

    public static int parse(String value) {
        return Parser.parseId(value);
    }
}
~~~

Đây là một class minh họa hợp lệ, giả định được đặt trong tệp `ProductCatalog.java` nếu dùng `public class`. Caller bên ngoài có thể tạo `new ProductCatalog.Entry()`, nhưng không được trực tiếp gọi `ProductCatalog.Parser` nếu không có quyền private access. Method `ProductCatalog.parse(...)` công bố một API có kiểm soát tới logic parser nội bộ.

**Vị trí đặt access modifier quan trọng:** top-level classes không được tùy tiện khai báo `private` hoặc `protected`; member nested classes có các quyền ấy theo quy tắc JLS.

Nên chọn visibility nhỏ nhất đủ dùng. Static nested helper không cần public chỉ vì “không cần Outer object”.

## 13. Tên kiểu và namespace: tại sao lồng class?

Khi một kiểu chỉ mang ý nghĩa trong ngữ cảnh của một kiểu khác, đặt tên `Outer.Nested` giúp tổ chức API:

~~~java
class Network {
    static class Endpoint {
    }

    static class Options {
    }
}
~~~

Đây là các định nghĩa hợp lệ. Hai class `Endpoint` và `Options` được đặt dưới tên logic `Network`, tránh cần các top-level names dài hoặc quá chung.

**Ưu điểm:**

- Nhóm các kiểu có liên quan gần nhau.
- Đặt visibility `private`/package-private nếu là chi tiết implementation.
- Sử dụng access đến private members của Outer khi thật sự cần.
- Dùng một tên class bao để làm điểm xuất phát của API, ví dụ `Parser.Token`, `Graph.Node`, `Response.Status`.

**Đánh đổi:** nếu Outer có quá nhiều nested classes lớn, file trở nên khó đọc và trách nhiệm class bị phình to. Static nested class không nên biến thành nơi chứa mọi utility không liên quan chỉ vì cú pháp cho phép.

## 14. Nested type name khác với package name

Trong source, `Outer.Nested` giống một tên có dấu chấm như `java.util.Map.Entry`, nhưng quan hệ là **member type**, không phải package `Outer`.

Nếu `Outer` thuộc package `com.example`, source có thể dùng `com.example.Outer.Nested`. Khi biên dịch, Java compiler thường sinh class files dạng:

~~~text
Outer.class
Outer$Nested.class
~~~

Tên chứa `$` ở đây là dạng binary-name convention cho member class trong Java/JVM. Trong source code thông thường, hãy dùng **`Outer.Nested`**, không tự viết `Outer$Nested` như thể đó là tên class source được khuyến nghị.

Đừng đoán binary name bằng cách nối chuỗi tùy ý để viết reflection code phức tạp; hãy dùng class token `Outer.Nested.class` khi có thể, hoặc `Class.getName()` và metadata API.

## 15. Chương trình hoàn chỉnh 5 — Class objects và tên lồng

Tạo tệp **`NestedClassMetadataDemo.java`**:

~~~java
class OuterType {
    static class StaticMember {
    }

    class InnerMember {
    }
}

public class NestedClassMetadataDemo {
    public static void main(String[] args) {
        Class<?> nested = OuterType.StaticMember.class;
        Class<?> inner = OuterType.InnerMember.class;

        System.out.println("nested simple="
                + nested.getSimpleName());
        System.out.println("nested binary=" + nested.getName());
        System.out.println("nested canonical="
                + nested.getCanonicalName());
        System.out.println("nested enclosing="
                + nested.getEnclosingClass().getSimpleName());

        System.out.println("inner binary=" + inner.getName());
        System.out.println("static nested is member="
                + nested.isMemberClass());
        System.out.println("inner is member=" + inner.isMemberClass());
        System.out.println("outer object required for token=false");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NestedClassMetadataDemo.java
java NestedClassMetadataDemo
~~~

**Stdout chính xác (các classes trong unnamed package như tệp trên):**

~~~text
nested simple=StaticMember
nested binary=OuterType$StaticMember
nested canonical=OuterType.StaticMember
nested enclosing=OuterType
inner binary=OuterType$InnerMember
static nested is member=true
inner is member=true
outer object required for token=false
~~~

Cả static nested member và inner member đều là **member classes**; `Class.isMemberClass()` không phân biệt chúng chỉ bằng boolean này.

Dòng cuối là **thông báo cố định do chương trình in**, minh họa rằng việc lấy `OuterType.StaticMember.class` không cần tạo OuterType instance. Muốn kiểm tra modifier static bằng reflection, có thể xem `Modifier.isStatic(nested.getModifiers())` thay vì đoán từ tên class.

## 16. Reflection có thể phân biệt modifier `static`

Class metadata cho phép kiểm tra:

~~~java
boolean staticMember = java.lang.reflect.Modifier.isStatic(
        OuterType.StaticMember.class.getModifiers());
~~~

Đây là một biểu thức minh họa đặt trong ngữ cảnh có `OuterType` như ví dụ trên. Với khai báo `static class StaticMember`, kết quả đúng là `true`.

Đối chiếu:

~~~java
boolean innerMember = java.lang.reflect.Modifier.isStatic(
        OuterType.InnerMember.class.getModifiers());
~~~

Với `class InnerMember` non-static, kết quả là `false`.

Điều này khác với `Class.isMemberClass()`: cả hai là member classes, nhưng chỉ một member có modifier static.

Không dùng reflection chỉ để “xem Nested có chạy hay không” trong ứng dụng bình thường. Khi đã biết kiểu ở compile time, việc tạo `new Outer.Nested()` rõ ràng hơn.

## 17. Generic Outer không tự truyền type parameter cho static nested class

Một nguồn lỗi phổ biến:

~~~java
class Registry<T> {
    static class Key {
        private final String value;

        Key(String value) {
            this.value = value;
        }
    }
}
~~~

Đây là class generic minh họa hợp lệ. `Registry<T>` có type parameter `T` **thuộc instance/class declaration của Registry**, nhưng `Key` là static nested class nên **không tự có `T` trong phạm vi type parameter của Outer**.

Code sau **cố ý không biên dịch** nếu bỏ chú thích:

~~~java
// class Registry<T> {
//     static class BadKey {
//         T payload; // T là type parameter của Registry, không hợp lệ ở đây.
//     }
// }
~~~

Nếu cần một type parameter cho nested class, hãy **khai báo ngay trên nested class**:

~~~java
class Registry<T> {
    static class Key<U> {
        private final U payload;

        Key(U payload) {
            this.payload = payload;
        }

        U payload() {
            return payload;
        }
    }
}
~~~

`Registry.Key<String>` là kiểu dùng được, hoàn toàn không phải `Registry<String>.Key`. Static member class không “đi kèm phiên bản generic Outer instance” theo nghĩa đó.

## 18. Chương trình hoàn chỉnh 6 — generic nested type độc lập

Tạo tệp **`GenericStaticNestedDemo.java`**:

~~~java
class Store<T> {
    private final T current;

    Store(T current) {
        this.current = current;
    }

    T current() {
        return current;
    }

    static class Receipt<U> {
        private final U item;

        Receipt(U item) {
            this.item = item;
        }

        U item() {
            return item;
        }
    }
}

public class GenericStaticNestedDemo {
    public static void main(String[] args) {
        Store<Integer> store = new Store<>(10);

        Store.Receipt<String> text =
                new Store.Receipt<>("paid");
        Store.Receipt<Integer> number =
                new Store.Receipt<>(42);

        System.out.println("store=" + store.current());
        System.out.println("text=" + text.item());
        System.out.println("number=" + number.item());
        System.out.println("receipt type="
                + text.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericStaticNestedDemo.java
java GenericStaticNestedDemo
~~~

**Stdout:**

~~~text
store=10
text=paid
number=42
receipt type=Receipt
~~~

`Store<T>` và `Receipt<U>` có **type parameters độc lập**. `Store.Receipt<String>` được tạo trực tiếp bằng `new Store.Receipt<>("paid")`, không cần cung cấp instance Store.

**Chú ý type erasure:** `Receipt<String>` và `Receipt<Integer>` vẫn có cùng runtime class `Store$Receipt`; type arguments không tạo ra những concrete runtime classes khác nhau.

## 19. Static nested class có thể chứa class khác và members riêng

Một static nested class có thể tiếp tục khai báo fields, constructors, methods và nested types hợp lệ của riêng nó:

~~~java
class Packet {
    static class Header {
        static final int VERSION = 1;

        private final int sequence;

        Header(int sequence) {
            this.sequence = sequence;
        }

        int sequence() {
            return sequence;
        }

        static class Codec {
            static String encode(Header header) {
                return VERSION + ":" + header.sequence();
            }
        }
    }
}
~~~

Đây là mã minh họa hợp lệ. Có thể dùng `Packet.Header.Codec.encode(new Packet.Header(5))`. Cả `Header` và `Codec` đều được khai báo static nested; không có implicit `Packet.this` hoặc `Header.this` trong Codec.

Dù các loại được lồng nhiều tầng, số lượng enclosing instances **không tăng lên** đối với static nested classes. Nếu code cần truy cập một instance Header, hãy truyền nó vào `encode(Header)` hoặc constructor.

Lồng sâu quá nhiều tầng có thể khiến API dài và khó đọc. Nên cân nhắc tách kiểu ra khi chúng có trách nhiệm độc lập hoặc dùng ở nhiều nơi.

## 20. Chương trình hoàn chỉnh 7 — nhiều tầng static nesting

Tạo tệp **`NestedLevelsDemo.java`**:

~~~java
class Transport {
    static class Frame {
        private final int number;

        Frame(int number) {
            this.number = number;
        }

        static class Formatter {
            static String render(Frame frame) {
                return "frame#" + frame.number;
            }
        }
    }
}

public class NestedLevelsDemo {
    public static void main(String[] args) {
        Transport.Frame frame = new Transport.Frame(7);
        String output =
                Transport.Frame.Formatter.render(frame);

        System.out.println(output);
        System.out.println("class="
                + frame.getClass().getSimpleName());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NestedLevelsDemo.java
java NestedLevelsDemo
~~~

**Stdout:**

~~~text
frame#7
class=Frame
~~~

Formatter có thể đọc `frame.number` qua reference tường minh theo quyền truy cập nesting. Nó không cần một Transport instance hoặc Frame instance **để được khởi tạo**; `render` ở ví dụ là static method và nhận đối tượng Frame làm tham số.

## 21. Trường hợp ứng dụng rất phổ biến: static nested Builder

Một **Builder** thuộc logic của class Outer nhưng không cần sở hữu một **Outer object đã tạo** trong suốt quá trình điền tham số. Vì vậy `public static class Builder` là lựa chọn phổ biến.

Ý tưởng:

~~~text
Tạo Outer.Builder (chưa có Outer object)
     |
     | ghi dữ liệu ứng viên vào Builder
     v
gọi build()
     |
     | constructor/factory của Outer kiểm tra invariant
     v
trả một Outer object hoàn chỉnh
~~~

Nếu Builder là non-static inner class, thông thường caller phải **tạo Outer trước**, trong khi mục đích của Builder là chuẩn bị dữ liệu **trước khi Outer tồn tại**. Một Builder static nested không gặp vòng phụ thuộc đó.

Tuy nhiên Builder có thể giữ mutable fields của chính nó — `static nested` không làm builder bất biến. Khi `build()` trả kết quả, phải bảo vệ mutable data (list, arrays) để sửa Builder sau đó không làm object đã xây đổi.

## 22. Chương trình hoàn chỉnh 8 — Builder static nested tạo immutable outer

Tạo tệp **`StaticNestedBuilderDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Course {
    private final String name;
    private final List<String> topics;

    private Course(Builder builder) {
        if (builder.name == null || builder.name.isBlank()) {
            throw new IllegalArgumentException("name rỗng");
        }
        name = builder.name;
        topics = List.copyOf(builder.topics);
    }

    String describe() {
        return name + "=" + topics;
    }

    static class Builder {
        private String name;
        private final List<String> topics = new ArrayList<>();

        Builder name(String next) {
            this.name = Objects.requireNonNull(next, "name");
            return this;
        }

        Builder addTopic(String topic) {
            topics.add(Objects.requireNonNull(topic, "topic"));
            return this;
        }

        Course build() {
            return new Course(this);
        }
    }
}

public class StaticNestedBuilderDemo {
    public static void main(String[] args) {
        Course.Builder builder = new Course.Builder()
                .name("Java")
                .addTopic("Class");

        Course first = builder.build();
        builder.addTopic("Object");
        Course second = builder.build();

        System.out.println("first=" + first.describe());
        System.out.println("second=" + second.describe());
        System.out.println("different=" + (first != second));

        try {
            first.describe();
            first.getClass();
            new Course.Builder().build();
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 StaticNestedBuilderDemo.java
java StaticNestedBuilderDemo
~~~

**Stdout:**

~~~text
first=Java=[Class]
second=Java=[Class, Object]
different=true
invalid=name rỗng
~~~

Giải thích:

1. `new Course.Builder()` chạy constructor của Builder, **không cần** Course instance.
2. Builder có thể đọc và thay đổi fields riêng `name`, `topics`.
3. Constructor riêng `Course(Builder)` được phép đọc private fields của Builder theo nesting access rules.
4. `Course` tạo `List.copyOf(builder.topics)`, nên việc Builder thêm topic tiếp theo không sửa object `first`.
5. Builder không phụ thuộc implicit `Course.this`; nó chỉ **truyền chính mình** vào constructor `Course` khi gọi `build()`.
6. Lệnh `new Course.Builder().build()` không có tên hợp lệ, nên constructor Course ném exception, không trả một Course lỗi.

**Lưu ý thiết kế:** `Course.Builder` trong ví dụ là package-private để tập trung bài học. Nếu library cung cấp Builder cho code từ package khác, API phải công bố `public static class Builder` và constructors/methods cần quyền `public` phù hợp. Một cách khác là thêm static factory `Course.builder()`.

## 23. Factory method và nested implementation `private`

Không phải nested class nào cũng cần người dùng tạo trực tiếp. Một Outer class có thể giấu implementation dạng `private static class` và trả interface:

~~~java
interface Formatter {
    String format(String input);
}

final class Formatters {
    private Formatters() {
    }

    static Formatter prefix(String prefix) {
        return new PrefixFormatter(prefix);
    }

    private static class PrefixFormatter implements Formatter {
        private final String prefix;

        PrefixFormatter(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String format(String input) {
            return prefix + input;
        }
    }
}
~~~

Đây là mã minh họa hợp lệ. Caller chỉ biết interface Formatter và method factory `Formatters.prefix(...)`. Class `PrefixFormatter` là chi tiết implementation **nằm dưới tên và quyền truy cập của Formatters**, không cần một Formatters instance.

Đây là cách tổ chức một implementation có phạm vi sử dụng hẹp, giúp outer public API gọn hơn và tránh xuất bản quá nhiều classes vào package.

## 24. Chương trình hoàn chỉnh 9 — private static nested implementation sau interface

Tạo tệp **`PrivateNestedImplementationDemo.java`**:

~~~java
interface Task {
    String run();
}

final class Tasks {
    private Tasks() {
    }

    static Task named(String name) {
        return new NamedTask(name);
    }

    private static final class NamedTask implements Task {
        private final String name;

        NamedTask(String name) {
            this.name = name;
        }

        @Override
        public String run() {
            return "run:" + name;
        }
    }
}

public class PrivateNestedImplementationDemo {
    public static void main(String[] args) {
        Task first = Tasks.named("A");
        Task second = Tasks.named("B");

        System.out.println("first=" + first.run());
        System.out.println("second=" + second.run());
        System.out.println("same=" + (first == second));
        System.out.println("runtime="
                + first.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PrivateNestedImplementationDemo.java
java PrivateNestedImplementationDemo
~~~

**Stdout:**

~~~text
first=run:A
second=run:B
same=false
runtime=NamedTask
~~~

`NamedTask` là `private static final class`: class bên ngoài không thể tham chiếu trực tiếp tới kiểu này bằng tên source từ những nơi không có access, nhưng `Tasks.named` có thể tạo và trả nó dưới interface `Task`.

`first.getClass()` vẫn phản ánh runtime class thật **NamedTask**, không phải Task; việc implementation class là private chỉ điều khiển source access, không xóa thông tin runtime class.

## 25. Static nested class giúp giảm tham chiếu ngầm tới Outer

Một non-static inner class có thể **giữ enclosing instance**. Nếu inner object sống lâu hơn outer object về mặt ứng dụng, tham chiếu ngầm ấy có thể khiến outer vẫn reachable và chưa được garbage collector thu hồi.

Static nested class **không tự có reference đó**, nên tránh được một nguồn **giữ object ngoài ý muốn** khi helper không cần outer state.

Tuy nhiên:

- Static nested class **có thể vẫn giữ Outer** nếu bạn chủ động khai báo field như `Machine.Command.machine`.
- Một static field nằm ở bất kỳ class nào nếu giữ references lâu dài vẫn có thể gây retention.
- GC không thu hồi theo “class còn sống hay không” một cách đơn giản; phụ thuộc **object reachability** và class loader lifecycle.
- Không nên quảng bá “static nested class không bao giờ leak memory”; ý đúng là **không có implicit enclosing-instance reference**.

Nếu helper cần trạng thái outer, việc non-static inner class gắn với outer có thể hoàn toàn đúng. Nếu không cần, static nested class thường giúp ownership dễ nhìn hơn.

## 26. Tại sao `Outer.Inner` đôi lúc cần cú pháp `outer.new Inner()`?

Điều này bắt nguồn từ cách tạo **non-static inner member class**, không áp dụng cho static nested member class.

Ví dụ:

~~~java
class House {
    class Room {
    }

    static class Address {
    }
}
~~~

Đây là định nghĩa minh họa. Khi caller có:

~~~java
House house = new House();
House.Room room = house.new Room();
House.Address address = new House.Address();
~~~

`Room` cần một House enclosing instance, trong khi `Address` không. Nếu đã có `house`, việc chọn Address từ class `House` vẫn không dùng `house.new Address()`.

Khi đọc lỗi compile-time kiểu “an enclosing instance that contains House.Room is required”, hãy kiểm tra xem bạn có dùng **inner class** như một **static nested class** hay không.

## 27. Những điều `static nested` KHÔNG có nghĩa

Một số ngộ nhận thường gặp:

| Ngộ nhận | Thực tế |
| --- | --- |
| “Nested object phải tạo Outer trước.” | Static nested class không cần enclosing instance |
| “Một nested class static nghĩa là chỉ có một object.” | Mỗi `new` vẫn tạo instance riêng |
| “Mọi field trong static nested class phải static.” | Có thể có instance fields và methods |
| “Static nested class không thể truy cập private fields Outer.” | Có thể theo access rules; **instance fields cần receiver** |
| “Static nested class có `Outer.this`.” | Không có implicit enclosing instance |
| “Nested class static tự kế thừa Outer.” | Không; lexical nesting **không phải extends** |
| “Nested class có quyền truy cập mọi object bất kể package.” | Access rules vẫn áp dụng; quyền trong nesting là theo quan hệ khai báo |
| “`new Outer.Nested()` gọi constructor Outer.” | Chỉ tạo Nested object, trừ logic khác được viết rõ |
| “Generic parameter của Outer tự có trong Nested.” | Static nested class phải khai báo type parameter riêng |
| “Nested class là package.” | Nó là member type của enclosing type |
| “Static nested class không giữ được Outer.” | Có thể giữ **reference tường minh** |
| “Static nested class luôn tốt hơn top-level class.” | Tùy phạm vi trách nhiệm và API |
| “Static nested class luôn immutable/thread-safe.” | Hoàn toàn không tự động |
| “Private static nested class hoàn toàn vô hình runtime.” | Runtime type vẫn tồn tại; source access được giới hạn |

## 28. Khởi tạo class và khởi tạo object: đừng nhầm

Java có **class initialization** cho static fields/blocks và **instance construction** cho mỗi object. Một static nested class có thể có static initialization riêng.

Điều quan trọng:

- Chỉ nhắc đến `Outer.Nested` trong source hoặc class literal không có nghĩa phải tạo Outer instance.
- Tạo `new Outer.Nested()` sẽ khởi tạo class Nested theo quy tắc JVM, nhưng **không tự tạo một Outer object**.
- Việc Nested là member của Outer không tự đảm bảo mọi static initialization block của Outer phải chạy trước khi Nested được khởi tạo; các lớp có quy tắc initialization dựa trên active use của chính chúng.
- Nếu code Nested chủ động truy cập một **non-constant static field** của Outer, tương tác đó có thể kích hoạt initialization của Outer.
- Việc gọi constructors khác nhau và class initialization là hai loại sự kiện khác nhau.

Không suy từ hai class files `Outer.class` và `Outer$Nested.class` rằng constructor Outer phải chạy để nested code tồn tại.

## 29. Chương trình hoàn chỉnh 10 — khởi tạo Nested không tạo Outer instance

Tạo tệp **`NestedInitializationDemo.java`**:

~~~java
class Host {
    static {
        System.out.println("Host static init");
    }

    Host() {
        System.out.println("Host constructor");
    }

    static class Worker {
        static {
            System.out.println("Worker static init");
        }

        Worker() {
            System.out.println("Worker constructor");
        }

        String work() {
            return "done";
        }
    }
}

public class NestedInitializationDemo {
    public static void main(String[] args) {
        System.out.println("begin");

        Host.Worker worker = new Host.Worker();
        System.out.println("work=" + worker.work());

        System.out.println("before Host");
        Host host = new Host();
        System.out.println("host class="
                + host.getClass().getSimpleName());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NestedInitializationDemo.java
java NestedInitializationDemo
~~~

**Stdout chính xác:**

~~~text
begin
Worker static init
Worker constructor
work=done
before Host
Host static init
Host constructor
host class=Host
~~~

Khi lần đầu tạo `Host.Worker`, JVM initialize Worker và chạy constructor Worker. Chưa có lý do phải initialize Host trong đoạn này, vì Worker không chủ động đọc static state của Host.

Đến `new Host()`, JVM initialize Host và chạy constructor Host. Điều này chứng minh riêng việc đặt Worker **bên trong declaration Host** không tự làm Host constructor hoặc static initializer chạy khi Worker object được tạo.

**Phạm vi kết luận:** ví dụ độc lập có class definitions đúng như trên. Nếu Worker truy cập `Host.someNonConstantStaticField` trong initialization, hành vi class initialization có thể khác theo quy tắc active use.

## 30. Cách chuyển một inner helper sang static nested class

Khi refactor một helper từ:

~~~java
class Outer {
    class Helper {
        void act() {
            doSomething();
        }
    }

    void doSomething() {
    }
}
~~~

sang `static class Helper`, hãy xem lại mọi truy cập instance members:

1. Xác định những field/method nào của Outer đang được gọi **ngầm**.
2. Nếu Helper không thật sự cần những giá trị đó, bỏ phụ thuộc.
3. Nếu cần một giá trị nhỏ, truyền giá trị ấy vào constructor/method Helper.
4. Nếu Helper cần làm việc với một Outer cụ thể, truyền một `Outer target` và ghi rõ ownership.
5. Thay mọi lời gọi `outer.new Helper()` bằng `new Outer.Helper(...)` khi API đã đổi.
6. Cập nhật tests về identity, lifecycle và reference retention.
7. Nếu Helper có type parameter phụ thuộc Outer, khai báo type parameter riêng trên static nested class.

Không nên biến mọi inner class thành static nested class theo máy móc: một inner class mô hình “phòng thuộc một ngôi nhà cụ thể” có thể thật sự cần enclosing House instance.

## 31. Quy tắc chọn inner hay static nested cho một bài toán

Có thể ra quyết định bằng câu hỏi:

**Helper cần một enclosing object cụ thể để hoạt động không?**

- **Không:** static nested class thường hợp lý, ví dụ `Configuration.Builder`, `Tree.Node` độc lập, `Parser.Token`, private adapter, immutable result, helper chỉ dùng static state hoặc input parameters.
- **Có:** non-static inner class có thể biểu đạt quan hệ gắn chặt với enclosing instance. Hoặc static nested class nhận Outer reference tường minh nếu muốn kiểm soát lifecycle rõ hơn.

**Helper cần tồn tại như một API public độc lập ở nhiều nơi không?**

- Có thể một **top-level class** sẽ dễ tái sử dụng, documentation và testing hơn.
- Nếu nó là một implementation detail nhỏ chỉ dùng bởi Outer, static nested private class giúp đóng gói tốt.

**Có cần generic type parameter của Outer không?**

- Non-static inner class có thể tham chiếu type parameter của Outer phù hợp.
- Static nested class không có quyền dùng trực tiếp type parameter đó; cần riêng `<U>` hoặc nhận dữ liệu dưới một API khác.

Hãy chọn dựa trên **dữ liệu và ownership**, không chỉ dựa vào số dòng code.

## 32. Các lỗi biên dịch thường gặp

| Lỗi/tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Tạo inner bằng `new Outer.Inner()` ngoài static context | Thiếu enclosing instance | Dùng `outer.new Inner()` |
| Tạo static nested bằng `outer.new Nested()` | Dùng cú pháp của inner class | Dùng `new Outer.Nested()` |
| Static nested code viết `Outer.this` | Không có Outer instance ngầm | Truyền reference Outer tường minh |
| Static nested code đọc `outerInstanceField` trực tiếp | Thiếu receiver | Dùng `target.field` sau khi có target |
| Dùng `private static class Helper` từ code ngoài | Không có private access | Dùng outer factory/API công khai |
| Dùng generic `T` của `Outer<T>` trong static Nested | T không nằm trong static context | Khai báo `Nested<U>` |
| Nghĩ Nested là subclass của Outer | Lexical nesting không phải inheritance | Dùng `extends` chỉ khi quan hệ kiểu đúng |
| Truy cập `new Outer.Nested()` nhưng constructor private | Constructor không truy cập được | Công bố constructor/factory thích hợp |
| Đọc instance field Outer dù nó là `private static`? | Nhầm quyền/receiver | Private static được đọc theo quyền nesting |
| Builder giữ mutable list rồi trả thẳng vào Outer | Built object bị alias với Builder | Snapshot `List.copyOf`/defensive copy |
| Tưởng nested class tự thread-safe | Static nesting không đồng bộ | Dùng immutable state/concurrency API |
| Tưởng static nested không bao giờ giữ Outer | Có field reference tường minh | Kiểm tra object reachability/ownership |

### Ví dụ lỗi cố ý, không phải mã runnable

~~~java
class Incorrect {
    private int number = 1;

    static class Nested {
        // int value() { return number; }
        // Sai: number là instance field của Incorrect.
    }
}
~~~

Muốn đọc `number`, cung cấp reference `Incorrect target` rồi dùng `target.number`, hoặc sửa thiết kế để Nested chỉ dùng những dữ liệu nó thật sự cần.

## 33. Debug bằng cách nhìn vào kiểu tham chiếu và vùng truy cập

Khi compiler báo không tìm thấy field hoặc không thể truy cập method từ nested class:

1. Xác định biến đang dùng là **class name** hay **object reference**.
2. Xác định field của Outer là **static** hay **instance**.
3. Xác định nested class là **static member** hay **non-static inner member**.
4. Nếu instance field, tìm object receiver: có `this`/enclosing `Outer.this` hợp lệ hay một parameter `Outer target`?
5. Xem access modifiers (`private`, package-private, `protected`, `public`) của member và vị trí caller.
6. Nếu outer class generic, xem type parameter nào thuộc scope nào.
7. Nếu constructor không truy cập được, xem visibility của constructor Nested chứ không chỉ visibility class Nested.
8. Với lỗi class-name, dùng `Outer.Nested` trong source và kiểm tra package/import.

Không xử lý lỗi thiếu enclosing instance bằng cách biến **instance field thành static** vô cớ; việc ấy thay đổi bản chất state từ riêng từng Outer object sang state chia sẻ toàn class.

## 34. Bài tập tự luyện

**Bài 1.** `class Outer { static class Nested {} }`: có cần tạo `Outer outer = new Outer();` trước khi gọi `new Outer.Nested()` không?

**Bài 2.** Vì sao `static class Nested` vẫn có thể có instance fields?

**Bài 3.** `Outer.Nested a = new Outer.Nested(); Outer.Nested b = new Outer.Nested();`. `a==b` thông thường là gì?

**Bài 4.** Nếu Nested chỉ đọc `private static int LIMIT` của Outer, có cần một instance Outer không?

**Bài 5.** Nếu Nested cần đọc `private int id` của **một Outer object cụ thể**, cách hợp lệ và rõ ràng là gì?

**Bài 6.** `Outer.this` có tồn tại trong static nested class không? Nó thường tồn tại ở loại member class nào?

**Bài 7.** `class Outer { class Inner {} }`: từ bên ngoài, cú pháp tạo Inner thông thường là gì?

**Bài 8.** `class Outer { static class Nested {} }`: `outer.new Nested()` có đúng không?

**Bài 9.** Vì sao Builder cho immutable Outer thường được khai báo `static`?

**Bài 10.** Một `Outer.Builder` giữ ArrayList và method `build()` chuyển thẳng list ấy sang object được công bố. Builder có thể làm object đã build đổi không?

**Bài 11.** Nested helper có quyền đọc private fields của Outer không? Phải phân biệt câu hỏi nào về instance receiver?

**Bài 12.** Trong `Outer<T>`, static nested class có tự nhìn thấy `T` không? Nếu muốn typed payload của Nested, nên làm gì?

**Bài 13.** Có thể tạo `Outer.Nested` với 10 objects mà không có Outer object nào không?

**Bài 14.** Tại sao một object `Outer.Nested` có thể vẫn giữ Outer sống lâu trong heap dù là static nested class?

**Bài 15.** `Outer.Nested.class.getName()` trong unnamed package thường có dạng nào?

**Bài 16.** `Class.isMemberClass()` có tự phân biệt static nested và non-static inner member không?

**Bài 17.** `new Outer.Nested()` có nhất thiết chạy constructor và static initializer của Outer không?

**Bài 18.** Nên dùng static nested private class hay top-level public class nếu kiểu chỉ là internal implementation của một factory?

**Bài 19.** Nếu helper cần phụ thuộc vào một object Outer riêng để gọi instance method, static nested class có thể nhận `Outer target` ở constructor không?

**Bài 20.** Static nested class có tự bảo đảm thread safety và immutability không?

**Bài 21.** Vì sao nên truyền dữ liệu cần thiết thay vì lưu cả Outer reference khi helper không cần ownership của toàn Outer?

**Bài 22.** Một public static nested class có constructor package-private; code khác package có luôn `new Outer.Nested()` được không?

**Bài 23.** Static nested class có kế thừa members của Outer chỉ vì được khai báo bên trong không?

**Bài 24.** Trong `Store<T>`, `Store.Receipt<U>` có type arguments độc lập không? Cần tạo Store để tạo Receipt không?

### Đáp án và giải thích

1. Không. Static nested class không gắn enclosing instance.
2. `static` quy định quan hệ nesting; instances của Nested vẫn là objects thông thường.
3. `false`, vì hai lệnh `new` tạo hai distinct objects.
4. Không; member là static và Nested có quyền truy cập private qua nesting rules.
5. Truyền `Outer target` rồi dùng `target.id`; có quyền access nhưng vẫn cần receiver.
6. Không; non-static inner member class có enclosing instance thích hợp nên có thể dùng `Outer.this`.
7. `outer.new Inner()` với `outer` là reference Outer hợp lệ.
8. Không, đó là syntax dành cho non-static inner class; dùng `new Outer.Nested()`.
9. Builder phải chuẩn bị dữ liệu **trước khi** Outer object được xây, nên không cần enclosing instance.
10. Có nếu built object và Builder chia sẻ mutable list; constructor nên chụp snapshot.
11. Có theo access rules; instance field vẫn phải có **receiver object cụ thể**.
12. Không. Static nested class phải khai báo type parameter riêng như `static class Nested<U>`.
13. Có. `new Outer.Nested()` không gọi constructor Outer.
14. Nếu nested instance giữ explicit reference tới Outer, hoặc liên kết khác khiến Outer vẫn reachable.
15. Thường `Outer$Nested` với member class, khác tên source `Outer.Nested`.
16. Không. Cả hai là member classes; xem modifiers nếu cần phân biệt static.
17. Không; Nesting không tự đòi tạo Outer object, và class initialization có quy tắc active use riêng.
18. Private static nested class thường phù hợp để ẩn implementation; factory trả interface.
19. Có. Đây là dependency tường minh, không phải enclosing instance ngầm.
20. Không. Thread safety và immutability phụ thuộc fields, synchronization, ownership và API.
21. Để tránh coupling và object retention không cần thiết; chỉ giữ những phụ thuộc thực sự cần.
22. Không. Class visibility và constructor visibility đều cần phù hợp.
23. Không. Nesting là quan hệ khai báo/phạm vi, không phải `extends`.
24. Có; `Receipt<U>` độc lập với `Store<T>`, và không cần Store instance.

## 35. Checklist sử dụng static nested class

- Lớp nằm bên trong một enclosing type theo mục đích rõ ràng?
- Đã chọn **static nested** thay vì non-static inner vì không cần implicit enclosing instance?
- Có dùng đúng `new Outer.Nested(...)`, không dùng `outer.new Nested(...)`?
- Có phân biệt type name `Outer.Nested` với tên package và với object reference?
- Nếu đọc instance state Outer, đã có **reference tường minh**?
- Quyền `private` không bị nhầm thành quyền có sẵn receiver?
- Instance fields của Nested không bị nhầm là static fields?
- Nếu nested class generic, đã khai báo type parameters riêng?
- Constructor visibility có phù hợp các caller không?
- Với helper riêng, đã cân nhắc `private static class` để giấu implementation?
- Với Builder, `build()` có bảo toàn invariant và tránh alias mutable?
- Nếu Nested giữ reference Outer, có hiểu lifecycle và retention không?
- Có giới hạn số tầng nested để code dễ đọc không?
- Nếu class cần tái sử dụng độc lập rộng rãi, đã cân nhắc top-level class?
- Có thử test tạo Nested **trước** bất kỳ Outer instance nào để xác nhận giả định?
- Có tránh gán nhầm cho static nested những bảo đảm về singleton, immutability hoặc thread safety?

## 36. Tài liệu chuẩn Java 17

- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): phân biệt inner class và ngữ cảnh enclosing instance.
- [JLS 17 §8.5 — Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5): khai báo member classes/interfaces.
- [JLS 17 §8.5.1 — Static Member Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5.1): static nested member classes và quy tắc scope.
- [JLS 17 §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): cú pháp `new`, qualified creation và inner classes.
- [JLS 17 §15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this` trong ngữ cảnh thích hợp.
- [JLS 17 §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): private/public/protected/member access.
- [JLS 17 §6.5 — Determining the Meaning of a Name](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5): cách Java phân giải tên đơn giản/qualified.
- [JLS 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): khi nào static initialization xảy ra.
- [Java SE 17 API — Class.getEnclosingClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getEnclosingClass()): metadata enclosing type.
- [Java SE 17 API — Class.isMemberClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isMemberClass()): phân biệt member class với local/anonymous classes.
- [Java SE 17 API — Modifier.isStatic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html#isStatic(int)): kiểm tra modifier static qua reflection.

**Kết luận:** `static nested class` là một **member class được nhóm bên trong enclosing type nhưng không mang enclosing instance ngầm định**. Bạn có thể tạo `new Outer.Nested()` mà không cần `new Outer()`. Nó vẫn là lớp đầy đủ với constructors, instance state, methods và visibility riêng. Nếu cần private static members của Outer, nó có thể truy cập theo access rules; nếu cần **instance state của một Outer cụ thể**, phải có reference tường minh. Hãy chọn static nested class khi một kiểu gắn với Outer về **tổ chức API** nhưng không cần gắn với một **Outer object** — đặc biệt hữu ích cho Builder, helper và private implementations.
