# Quan hệ sử dụng, liên kết và sở hữu đối tượng trong Java

Trong lập trình hướng đối tượng (OOP), các lớp không tồn tại độc lập: một đối tượng có thể **sử dụng** đối tượng khác để thực hiện một thao tác, **giữ tham chiếu** đến đối tượng khác trong thời gian dài, hoặc **chịu trách nhiệm tạo, quản lý và kết thúc vòng đời** của những đối tượng thành phần.

Ba câu hỏi cốt lõi khi thiết kế là:

1. **Sử dụng (dependency):** Lớp A chỉ cần dịch vụ của B tại một thời điểm hay trong một thao tác không?
2. **Liên kết (association):** Một object A có quan hệ ổn định với object B và cần lưu/điều hướng tới B không?
3. **Sở hữu (ownership/composition):** Object A có chịu trách nhiệm kiểm soát vòng đời, tính toàn vẹn và quyền thay đổi của object B không?

Trong UML, các khái niệm thường được trình bày dưới tên **dependency**, **association**, **aggregation** và **composition**. Trong Java, chúng thường được biểu đạt bằng **tham số, biến cục bộ, field tham chiếu, constructor injection, collection**, cùng những **hợp đồng về vòng đời**. Java **không có từ khóa riêng `composition` hoặc `aggregation`**: ý nghĩa sở hữu chủ yếu do thiết kế/API xác lập.

## 1. Bản đồ tổng quan

| Quan hệ | Ý nghĩa thường dùng | Biểu hiện Java tiêu biểu | Câu hỏi thiết kế |
| --- | --- | --- | --- |
| **Dependency (uses)** | A cần B để thực hiện công việc | B là tham số method; biến local; gọi dịch vụ B | A có **sử dụng** B không? |
| **Association** | A có mối liên hệ với B | Field `B`, `Optional<B>`, `List<B>` hoặc truy vấn B | A có **biết/giữ liên hệ** với B không? |
| **Aggregation** | Whole–part **chia sẻ**, phần có thể tồn tại độc lập | A giữ các object B được tạo/sở hữu bên ngoài | B có thể thuộc nhiều whole hoặc sống độc lập? |
| **Composition** | Whole–part **sở hữu mạnh**, vòng đời phần phụ thuộc whole trong mô hình | A tự tạo/quản lý B; API hạn chế chia sẻ và lộ mutable reference | Ai **quyết định vòng đời** B? |

Ví dụ trong ứng dụng đào tạo:

- `ReportService.generate(report, formatter)` **sử dụng** một `Formatter` do caller cung cấp.
- `Course` giữ field `Instructor instructor` để biết người dạy: **association**.
- `Department` tập hợp `Employee` có thể chuyển phòng ban hoặc tồn tại độc lập: **shared aggregation** nếu mô hình nghiệp vụ coi đó là whole–part chia sẻ.
- `Order` tạo và kiểm soát các `OrderLine` không có danh tính/vòng đời nghiệp vụ độc lập: **composition**.

Không nên hiểu bảng như công thức tự động “hễ có field là composition”. Một field chỉ chứng minh rằng object **giữ tham chiếu**; không đủ để kết luận ai sở hữu nó.

### Tương tác, cấu trúc và vòng đời

Một cách phân loại hữu ích:

```text
             TƯƠNG TÁC NGẮN HẠN
        A ------ uses ------> B
                  dependency

             LIÊN HỆ CẤU TRÚC
        A ------- knows ----- B
                  association

             QUAN HỆ WHOLE–PART
        Whole ----- shares ---> Part
                 aggregation

        Whole ----- owns -----> Part
                 composition
```

Trong thực tế, một quan hệ có thể đồng thời thể hiện nhiều khía cạnh: A **phụ thuộc** vào interface B ở mức biên dịch và **giữ một liên kết** tới instance B ở runtime. Khi vẽ UML, hãy chọn góc nhìn và mức trừu tượng phù hợp, tránh coi các thuật ngữ là bốn “kiểu field Java” tách biệt tuyệt đối.

## 2. Đơn vị phân tích: class hay object?

**Class** định nghĩa kiểu và hành vi; **object** là thể hiện cụ thể được tạo lúc chạy.

```java
class Author {
    private final String name;

    Author(String name) {
        this.name = name;
    }
}

class Book {
    private final Author author;

    Book(Author author) {
        this.author = author;
    }
}
```

Ở mức **class diagram**, ta nói `Book` có association với `Author`.

Ở mức **object diagram**, ta có:

```text
book1:Book -----> authorA:Author
book2:Book -----> authorA:Author
```

Hai object `Book` đang tham chiếu **cùng một object `Author`**. Chúng không tạo hai Author chỉ vì có hai field mang tên `author`.

Điều này đặc biệt quan trọng khi bàn về sở hữu: **có tham chiếu không đồng nghĩa có quyền sở hữu độc quyền**. Nếu cùng một `Author` được hai `Book` dùng chung, mô hình không nên mặc định rằng xóa một Book sẽ xóa Author.

## 3. Dependency: quan hệ sử dụng

**Dependency** mô tả việc một phần tử mô hình **cần đến** phần tử khác để thực hiện một hành vi hoặc khai báo của nó. Ở mức code, dạng thường gặp nhất là **method nhận object cần dùng qua tham số và không giữ lại**.

Ví dụ:

```java
interface Formatter {
    String format(String text);
}

class GreetingService {
    String greet(String name, Formatter formatter) {
        return formatter.format("Xin chào " + name);
    }
}
```

`GreetingService` dùng `Formatter` trong method `greet`. Nó **không nhất thiết giữ field `Formatter`**. Caller được quyền cung cấp formatter khác nhau ở các lần gọi.

Điểm nhận biết:

- B là tham số, biến cục bộ hoặc object được gọi trong một thao tác.
- A cần một API của B để hoàn thành công việc.
- Khi lời gọi kết thúc, A có thể không giữ tham chiếu đến B.
- Sự thay đổi interface B có thể ảnh hưởng việc biên dịch/hoạt động của A.

**Không phải mỗi `import` là một quan hệ object runtime.** Import là cơ chế sử dụng tên trong source; nó có thể góp phần tạo dependency ở mức mã nguồn, nhưng không chứng minh rằng hai instance có liên hệ lâu dài.

### Ví dụ Java 17 chạy được: dependency qua tham số

Lưu **`DependencyDemo.java`**:

```java
interface Formatter {
    String format(String text);
}

final class UppercaseFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}

final class BracketFormatter implements Formatter {
    @Override
    public String format(String text) {
        return "[" + text + "]";
    }
}

final class GreetingService {
    String greet(String name, Formatter formatter) {
        return formatter.format("Xin chào " + name);
    }
}

public class DependencyDemo {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();

        System.out.println(
                service.greet("An", new UppercaseFormatter()));
        System.out.println(
                service.greet("Bình", new BracketFormatter()));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 DependencyDemo.java
java DependencyDemo
```

**Stdout:**

```text
XIN CHÀO AN
[Xin chào Bình]
```

`GreetingService` được **tái sử dụng** với hai `Formatter` khác nhau. Đây là ví dụ **method injection**: dependency được cung cấp tại lời gọi, không bị giữ làm trạng thái của service.

### Khi nào dùng dependency ngắn hạn?

- Hàm xử lý nhận strategy/callback chỉ dùng trong một tác vụ.
- Utility method xử lý object được truyền vào.
- Validator/formatter tùy chọn cho từng lần gọi.
- Service thao tác trên repository/session do tầng điều phối sở hữu trong một phạm vi ngắn.

Nếu A cần dùng B trong **toàn bộ vòng đời của A**, field association/constructor injection thường phù hợp hơn.

## 4. Association: liên kết giữa các đối tượng

**Association** là quan hệ cấu trúc: một object có thể **biết** và điều hướng tới object khác trong mô hình.

Ví dụ:

```java
class Course {
    private Instructor instructor;

    Course(Instructor instructor) {
        this.instructor = instructor;
    }
}
```

Field `instructor` cho thấy mỗi `Course` giữ một tham chiếu `Instructor` ở trạng thái hiện tại. Đây là **unidirectional association** từ `Course` sang `Instructor` nếu instructor không giữ tham chiếu ngược.

Association không khẳng định:

- Course tạo Instructor.
- Course sở hữu độc quyền Instructor.
- Instructor bị hủy khi Course không còn được dùng.
- Một Instructor chỉ được tham gia một Course.

Để khẳng định các ý trên, cần **hợp đồng nghiệp vụ và API** riêng.

### Điều hướng một chiều và hai chiều

Một chiều:

```text
Course --------> Instructor
```

Hai chiều:

```text
Course <-------> Instructor
```

Trong Java, một association hai chiều thường cần **hai phía lưu tham chiếu** hoặc một cơ chế truy vấn tương đương, nhưng phải đồng bộ invariant của quan hệ.

Ví dụ hai chiều thường thấy: `Department` biết `Employee` và `Employee` biết `Department`. Khi chuyển nhân viên sang phòng khác, hệ thống phải bảo đảm **cả hai phía** được cập nhật thống nhất.

**Không nên tạo hai setter độc lập** cho phép client thay một phía mà quên phía còn lại.

## 5. Ví dụ association một chiều: Course – Instructor

Lưu **`AssociationDemo.java`**:

```java
import java.util.Objects;

final class Instructor {
    private final String name;

    Instructor(String name) {
        this.name = Objects.requireNonNull(name, "name");
    }

    String name() {
        return name;
    }
}

final class Course {
    private final String title;
    private Instructor instructor;

    Course(String title, Instructor instructor) {
        this.title = Objects.requireNonNull(title, "title");
        this.instructor = Objects.requireNonNull(instructor, "instructor");
    }

    void changeInstructor(Instructor next) {
        instructor = Objects.requireNonNull(next, "next");
    }

    String description() {
        return title + " - " + instructor.name();
    }
}

public class AssociationDemo {
    public static void main(String[] args) {
        Instructor an = new Instructor("An");
        Instructor binh = new Instructor("Bình");

        Course java = new Course("Java", an);
        Course sql = new Course("SQL", an);

        System.out.println(java.description());
        System.out.println(sql.description());

        java.changeInstructor(binh);
        System.out.println(java.description());
        System.out.println(sql.description());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AssociationDemo.java
java AssociationDemo
```

**Stdout:**

```text
Java - An
SQL - An
Java - Bình
SQL - An
```

Đặc điểm:

1. Cả `java` và `sql` ban đầu đều **liên kết với cùng Instructor An**.
2. `java.changeInstructor(binh)` thay association của **một Course**, không ảnh hưởng Course khác.
3. Instructor tồn tại như object độc lập, do caller tạo và cấp vào Course.
4. `Course` không có logic tạo hay đóng `Instructor`. Vì vậy **không nên gọi đây là composition** chỉ do có field.

`Objects.requireNonNull` bảo đảm Course trong ví dụ luôn có Instructor khác null. Nếu môn học có thể chưa được phân giảng viên, mô hình cần thay điều kiện ấy bằng cardinality `0..1` và API phù hợp.

## 6. Cardinality / multiplicity: số lượng đối tượng tham gia

Trong UML, một association có thể chỉ rõ **multiplicity** ở các đầu liên kết:

| Multiplicity | Cách đọc | Mô hình Java có thể chọn |
| --- | --- | --- |
| `1` | Chính xác một | Field bắt buộc không null |
| `0..1` | Không hoặc một | Nullable field hoặc `Optional` ở API đọc |
| `0..*` hoặc `*` | Không hoặc nhiều | `List<T>`/`Set<T>` có thể rỗng |
| `1..*` | Một hoặc nhiều | Collection + validation không rỗng |
| `2..5` | Từ hai tới năm | Collection + validate số lượng |
| `n` | Đúng n | Collection/mảng + invariant kích thước |

**Java type không tự enforce UML multiplicity.** Khai báo `List<Student> students` không có nghĩa “ít nhất một Student”; list vẫn có thể rỗng. Tương tự, khai báo `Instructor instructor` không tự cấm null.

Ví dụ invariant:

```java
Course(String title, Instructor instructor) {
    this.title = Objects.requireNonNull(title);
    this.instructor = Objects.requireNonNull(instructor);
}
```

Tuyên bố “Course luôn có đúng một Instructor” trở nên đáng tin hơn nếu mọi đường tạo/cập nhật đều kiểm tra non-null và class kiểm soát việc lộ trạng thái.

### Navigability không giống cardinality

- **Navigability:** từ object nào có thể đi đến object nào qua mô hình?
- **Multiplicity:** một object ở đầu này có thể gắn với bao nhiêu objects đầu kia?

Một association `Course -> Instructor` có thể có multiplicity `1` ở đầu Instructor, trong khi một Instructor có thể dạy `0..*` Courses. Đây là hai thông tin khác nhau.

## 7. Association hai chiều: giữ hai phía đồng bộ

Nếu `Department` giữ tập nhân viên và mỗi `Employee` giữ phòng ban, các cập nhật phải bảo đảm:

```text
employee.department == department
  tương đương
department.members chứa employee
```

Tránh API sai:

```java
employee.setDepartment(newDepartment);
// Nhưng newDepartment.members không được cập nhật.
```

Có hai hướng thiết kế:

1. **Một phía là nguồn sự thật**, phía kia truy vấn thay vì giữ tham chiếu lặp lại.
2. **Giữ hai phía nhưng chỉ có một thao tác liên kết/di chuyển quản lý toàn bộ thay đổi**.

Ví dụ hoàn chỉnh bên dưới dùng phía `Employee.transferTo` để điều phối. Nó minh họa cách thiết kế association; chưa giải quyết các ràng buộc transaction/thread-safety cho hệ thống nhiều luồng.

### Chương trình: association hai chiều có quản lý

Lưu **`BidirectionalAssociationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Department {
    private final String name;
    private final List<Employee> employees = new ArrayList<>();

    Department(String name) {
        this.name = Objects.requireNonNull(name);
    }

    String name() {
        return name;
    }

    void addInternal(Employee employee) {
        if (!employees.contains(employee)) {
            employees.add(employee);
        }
    }

    void removeInternal(Employee employee) {
        employees.remove(employee);
    }

    int size() {
        return employees.size();
    }
}

final class Employee {
    private final String name;
    private Department department;

    Employee(String name) {
        this.name = Objects.requireNonNull(name);
    }

    void transferTo(Department next) {
        if (department == next) {
            return;
        }

        if (department != null) {
            department.removeInternal(this);
        }

        department = next;

        if (next != null) {
            next.addInternal(this);
        }
    }

    String location() {
        return name + "@" + (department == null
                ? "NONE" : department.name());
    }
}

public class BidirectionalAssociationDemo {
    public static void main(String[] args) {
        Department dev = new Department("DEV");
        Department qa = new Department("QA");
        Employee an = new Employee("An");

        an.transferTo(dev);
        System.out.println(an.location());
        System.out.println("DEV: " + dev.size());

        an.transferTo(qa);
        System.out.println(an.location());
        System.out.println("DEV: " + dev.size());
        System.out.println("QA: " + qa.size());

        an.transferTo(null);
        System.out.println(an.location());
        System.out.println("QA: " + qa.size());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 BidirectionalAssociationDemo.java
java BidirectionalAssociationDemo
```

**Stdout:**

```text
An@DEV
DEV: 1
An@QA
DEV: 0
QA: 1
An@NONE
QA: 0
```

**Giải thích:** `Employee.transferTo` điều phối tháo quan hệ cũ, cập nhật trường `department`, rồi thêm nhân viên vào Department mới. Nếu chỉ có một `Department.employees.add(an)` độc lập mà không cập nhật `an.department`, association có thể lệch.

### Hạn chế cần nói rõ

Ví dụ để `addInternal`/`removeInternal` ở mức package-private cho ngắn gọn. Với thư viện lớn, mã khác cùng package vẫn có thể gọi các method ấy và làm invariant sai. Có thể dùng một lớp quản lý association riêng, giới hạn module/package, hoặc thiết kế mô hình **một nguồn sự thật** để giảm rủi ro.

Ngoài ra, `List.contains`/`remove` dùng `equals`; ví dụ `Employee` không override `equals` nên so sánh theo identity. Nếu `equals` theo business key, phải xem kỹ nguy cơ trùng/xóa nhầm và chi phí tìm kiếm.

## 8. Association không phải inheritance

Hai quan hệ rất dễ lẫn:

- `class Manager extends Employee`: **is-a**, quan hệ kiểu/kế thừa.
- `class Employee { Department department; }`: **has-a/knows-a**, quan hệ association.
- `class ReportService { void generate(Printer p) { ... } }`: **uses-a**, dependency.

Một `Car` có `Engine` không có nghĩa `Car extends Engine`. Một `Student` có `Address` không có nghĩa `Student is-a Address`.

**Nguyên tắc:** dùng inheritance khi có subtype thật sự thỏa hợp đồng của supertype; dùng association/composition khi đối tượng **cộng tác hoặc chứa** những đối tượng khác.

Một câu tiếng Việt “có một” có thể gợi ý has-a, nhưng vẫn cần xác định **mức độ sở hữu/vòng đời** chứ chưa đủ để kết luận là composition.

## 9. Aggregation: whole–part có thể chia sẻ

UML **shared aggregation** thường được biểu diễn bằng **hình thoi rỗng** ở đầu whole. Ý tưởng phổ biến là một tổng thể giữ tập các phần, nhưng phần có thể **tồn tại độc lập hoặc được dùng trong nhiều tổng thể**.

Ví dụ mô hình tổ chức:

- `Department` tập hợp `Employee`.
- Một `Employee` vẫn là một cá thể nghiệp vụ khi chuyển phòng.
- Xóa/sáp nhập Department không nhất thiết xóa Employee.

```text
Department ◇──────── Employee
      whole             part
```

**Cảnh báo về UML:** shared aggregation có semantics yếu và cách sử dụng thực tế không thống nhất giữa các mô hình. Đừng suy ra một tập ràng buộc runtime rất cụ thể chỉ từ hình thoi rỗng. Khi ownership/lifecycle không rõ, **association với multiplicity và mô tả nghiệp vụ** thường dễ hiểu hơn.

### Aggregation không có cú pháp Java riêng

```java
class Department {
    private final List<Employee> employees;
}
```

Dòng này **chưa chứng minh** aggregation. Nó có thể là association nhiều-nhiều, shared aggregation, hoặc cấu trúc internal cache; cần xem API, thực tế object ownership và hợp đồng nghiệp vụ.

## 10. Ví dụ aggregation: nhiều nhóm chia sẻ cùng thành viên

Lưu **`AggregationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Member {
    private final String name;

    Member(String name) {
        this.name = Objects.requireNonNull(name);
    }

    String name() {
        return name;
    }
}

final class Team {
    private final String name;
    private final List<Member> members = new ArrayList<>();

    Team(String name) {
        this.name = Objects.requireNonNull(name);
    }

    void add(Member member) {
        members.add(Objects.requireNonNull(member));
    }

    String describe() {
        return name + ": " + members.stream()
                .map(Member::name)
                .toList();
    }
}

public class AggregationDemo {
    public static void main(String[] args) {
        Member an = new Member("An");
        Member binh = new Member("Bình");

        Team api = new Team("API");
        Team quality = new Team("QA");

        api.add(an);
        api.add(binh);
        quality.add(an);

        System.out.println(api.describe());
        System.out.println(quality.describe());

        api = null; // Chỉ bỏ một tham chiếu tới Team API.
        System.out.println("Member còn được dùng: " + an.name());
        System.out.println(quality.describe());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AggregationDemo.java
java AggregationDemo
```

Stdout:

```text
API: [An, Bình]
QA: [An]
Member còn được dùng: An
QA: [An]
```

Phân tích:
- `an` do caller tạo **trước khi** được thêm vào các Team.
- Cùng object `an` được liên kết từ hai Team.
- `api = null` chỉ làm biến local `api` không còn giữ reference; nó **không có nghĩa JVM đã lập tức xóa Team**, và cũng không phá hủy `an`.
- `quality` vẫn tham chiếu đến `an` nên có thể sử dụng bình thường.

Mục tiêu ví dụ là mô hình **phần có vòng đời độc lập với một whole**, chứ không chứng minh chính xác thời điểm garbage collector giải phóng memory.

## 11. Composition: sở hữu mạnh trong whole–part

Trong UML, **composition** thường được biểu diễn bằng **hình thoi đặc** ở đầu whole:

```text
Order ◆──────── OrderLine
 whole              part
```

Ý tưởng chung:

- Whole là nơi kiểm soát **vòng đời nghiệp vụ** của part.
- Trong mô hình tại một thời điểm, một part instance có **tối đa một composite owner** theo semantics composition.
- Khi whole bị xóa/đóng theo nghiệp vụ, các part lệ thuộc cũng được xử lý phù hợp (xóa, hủy kết nối, hoàn tất giao dịch, giải phóng tài nguyên...).
- Part thường không được xem là một thực thể có vòng đời độc lập hoàn toàn trong domain.

**Quan trọng:** JVM không ép những ràng buộc trên chỉ bằng việc bạn viết field `private final Line line;`. Java reference có thể được chia sẻ nếu bạn để lộ ra ngoài. Quyền sở hữu là **hợp đồng và invariant cần thực thi qua API**.

### Composition không có nghĩa mọi part phải được `new` ở đúng constructor whole

Một Order có thể được tạo từ input data đã tồn tại, hoặc nhận object do factory tạo rồi **chuyển giao quyền sở hữu** theo hợp đồng. Điều quan trọng là **sau chuyển giao**, owner kiểm soát vòng đời và không còn những đường cập nhật trái phép.

Vì vậy tiêu chí “A tạo B bằng `new`” là **dấu hiệu thường gặp**, không phải định nghĩa đầy đủ hoặc điều kiện cần duy nhất của composition.

## 12. Ví dụ composition: Order sở hữu OrderLine

Thiết kế: Order không trả các mutable `OrderLine` internal cho caller. Một order line không có API công khai để tồn tại độc lập như thực thể bên ngoài, và `Order` quản lý việc thêm item.

Lưu **`CompositionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Order {
    private record Line(String sku, int quantity, int unitPrice) {
        Line {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }

        long amount() {
            return (long) quantity * unitPrice;
        }
    }

    private final List<Line> lines = new ArrayList<>();

    void addLine(String sku, int quantity, int unitPrice) {
        lines.add(new Line(sku, quantity, unitPrice));
    }

    long total() {
        long result = 0;
        for (Line line : lines) {
            result += line.amount();
        }
        return result;
    }

    int lineCount() {
        return lines.size();
    }
}

public class CompositionDemo {
    public static void main(String[] args) {
        Order order = new Order();

        order.addLine("BOOK", 2, 120);
        order.addLine("PEN", 3, 10);

        System.out.println("Số dòng: " + order.lineCount());
        System.out.println("Tổng: " + order.total());
    }
}
```

```bash
javac -encoding UTF-8 CompositionDemo.java
java CompositionDemo
```

**Stdout:**

```text
Số dòng: 2
Tổng: 270
```

Đây là **mô hình composition** hợp lý:
1. `Order` tự tạo từng `Line` qua `addLine`.
2. `Line` là nested record `private`, không lộ ra ngoài như một mutable child public.
3. Dữ liệu sku/quantity/unitPrice được validate khi tạo line.
4. Caller không thể `order.lines.clear()` vì field private và không có getter trả list.
5. `Order` chịu trách nhiệm quản lý tập line trong domain model.

**Giới hạn:** không có “ngôn ngữ tự xóa OrderLine khi Order biến mất”. Nếu `Order` và những `Line` của nó không còn được tham chiếu bởi mã có thể truy cập, garbage collector *có thể* thu hồi memory vào thời điểm JVM quyết định. **Domain ownership** và **memory reclamation** là hai cơ chế khác nhau.

### Vì sao dùng kiểu `long` cho amount?

Phép nhân được nâng lên `long` nhờ ép `(long) quantity`, tránh tràn **int** trong tích trung gian đối với miền giá trị của hai tham số int (tích của hai int dương thuộc phạm vi long). Tuy nhiên **tổng nhiều dòng** vẫn có thể tràn long nếu nghiệp vụ cho phép số lượng cực lớn. Khi xử lý tiền thật nên xem `BigDecimal`, đơn vị tiền tệ, overflow policy và transaction invariants. Ví dụ tập trung vào composition, không thay thế mô hình tiền tệ production.

## 13. Aggregation và composition: khác nhau ở hợp đồng, không ở kiểu field

Xét hai khai báo giống nhau:

```java
class Team {
    private final List<Member> members = new ArrayList<>();
}
```

và:

```java
class Order {
    private final List<Line> lines = new ArrayList<>();
}
```

Về cú pháp, cả hai giữ một `List`. Nhưng ý nghĩa domain khác:

| Tiêu chí | Team – Member (aggregation/association) | Order – Line (composition) |
| --- | --- | --- |
| Ai tạo part? | Caller/hệ thống nhân sự có thể tạo Member độc lập | Order kiểm soát việc tạo Line |
| Part có danh tính nghiệp vụ độc lập? | Có thể có | Thường không |
| Part có thể tham gia nhiều whole? | Có thể, tùy domain | Thường không đồng thời |
| Xóa whole có nghĩa xóa part? | Thường không | Thường xóa/đóng part cùng vòng đời whole |
| API có thể cho chia sẻ reference part? | Thường được nếu hợp đồng cho phép | Thường hạn chế để bảo vệ ownership |
| Java field biểu hiện | `List<Member>` | `List<Line>` |
| Java có tự ép semantics? | Không | Không |

**Không thể suy luận** aggregation hay composition chỉ từ `List<T>`, `final`, `private` hoặc một lời gọi `new`. Hãy xác định ngữ nghĩa của ứng dụng.

## 14. Sở hữu đối tượng là gì trong Java?

**Object ownership** là sự phân công **ai chịu trách nhiệm quản lý object**. Có nhiều khía cạnh:

- **Construction ownership:** ai tạo object hoặc có quyền chọn implementation?
- **Mutation ownership:** ai được phép thay state, bảo vệ invariant?
- **Lifetime ownership:** ai quyết định khi nào object không còn hợp lệ trong nghiệp vụ?
- **Resource ownership:** ai phải gọi `close()` cho kết nối/tệp/stream?
- **Concurrency ownership:** thread hoặc thành phần nào được phép ghi?
- **Publication ownership:** ai cho phép lộ reference ra bên ngoài?

Các khía cạnh này **có thể không trùng nhau**. Ví dụ caller tạo một `OutputStream`, truyền cho service để ghi. Service **sử dụng** stream nhưng caller vẫn **sở hữu trách nhiệm đóng** stream. Nếu service đóng stream không có thỏa thuận, nó đã vi phạm ownership contract.

### Java không có hệ thống move ownership tổng quát như Rust

Java không có modifier tổng quát đảm bảo tại compile time rằng mọi reference mutable là **độc quyền** hoặc đã được chuyển quyền sở hữu theo kiểu linear/affine. Một object có thể có nhiều aliases.

Do vậy quy tắc “part chỉ có một owner” cần được thực hiện bằng:
- API giới hạn;
- Defensive copying;
- Immutable value objects;
- Factories/builders với hợp đồng rõ;
- Các guard kiểm tra trạng thái;
- Thiết kế vòng đời tài nguyên;
- Tests và review.

Đừng xem `final` là ownership keyword: `final` chủ yếu giới hạn **gán lại biến/field**, không cấm sửa mutable object được tham chiếu.

## 15. Aliasing: nhiều reference đến cùng object

```java
List<String> source = new ArrayList<>();
List<String> alias = source;

alias.add("Java");
System.out.println(source); // [Java]
```

Hai biến cùng trỏ **một list**. Nếu một class lưu trực tiếp tham số mutable:

```java
class Registry {
    private final List<String> values;

    Registry(List<String> values) {
        this.values = values; // Chia sẻ alias với caller.
    }
}
```

thì caller có thể thay nội dung `values` sau khi constructor kết thúc. Việc `Registry.values` là `private final` không đủ để kiểm soát state.

Đây là một rủi ro khi cố biểu đạt composition bằng “giữ field private final” nhưng caller vẫn sở hữu reference đến object mutable.

### Phân biệt quyền sở hữu theo domain với alias

Có thể hai tham chiếu cùng trỏ một object mà hệ thống vẫn **quy ước chỉ một chủ sở hữu được mutate**. Nhưng nếu API cho phép caller vi phạm, hợp đồng sở hữu rất khó kiểm chứng.

Khi cần đặc tính bảo vệ mạnh, dùng immutable data hoặc copy tại ranh giới ownership thay vì phụ thuộc lời hứa ngầm.

## 16. Defensive copy ở constructor và getter

Nếu cần snapshot độc lập cho collection chứa các immutable values như `String`, có thể dùng `List.copyOf`.

Ví dụ:

```java
final class Playlist {
    private final List<String> tracks;

    Playlist(List<String> source) {
        tracks = List.copyOf(source);
    }

    List<String> tracks() {
        return tracks;
    }
}
```

Tại sao có thể trả `tracks` trực tiếp?
- `List.copyOf` tạo danh sách **unmodifiable** theo hợp đồng.
- `String` là immutable.
- Các thay đổi cấu trúc vào `source` mutable sau khi copy không tự cập nhật snapshot.

**Đừng gọi `List.copyOf` là deep copy.** Nếu elements là `MutableAddress`, các object phần tử có thể vẫn được chia sẻ; việc caller đổi field của một element ảnh hưởng đến kết quả đọc từ list snapshot.

### `Collections.unmodifiableList` là view, không phải snapshot

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
```

View không cho sửa trực tiếp qua nó, nhưng vẫn quan sát backing list. Nếu whole cần kiểm soát hoàn toàn các changes, view có thể không đủ nếu caller giữ alias đến backing list.

## 17. Chương trình runnable: bảo vệ ownership của collection

Lưu **`OwnershipCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class SnapshotGroup {
    private final List<String> names;

    SnapshotGroup(List<String> source) {
        names = List.copyOf(source);
    }

    List<String> members() {
        return names;
    }
}

public class OwnershipCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        SnapshotGroup group = new SnapshotGroup(source);
        source.add("Bình");

        System.out.println("source = " + source);
        System.out.println("group = " + group.members());

        try {
            group.members().add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("snapshot không cho sửa");
        }
    }
}
```

```bash
javac -encoding UTF-8 OwnershipCopyDemo.java
java OwnershipCopyDemo
```

**Stdout:**

```text
source = [An, Bình]
group = [An]
snapshot không cho sửa
```

Bài học: ownership cần cả **kiểm soát đầu vào** (không giữ mutable source alias) và **kiểm soát đầu ra** (không trả backing mutable collection). Đây là cách giúp một whole bảo vệ invariant của mình.

## 18. Vòng đời object Java và garbage collection

Một câu thường được nói khi dạy composition là: *“Whole bị hủy thì part cũng bị hủy.”* Câu ấy mô tả **vòng đời trong mô hình UML/domain**, **không phải lệnh Java runtime tự gọi destructor**.

Java có **garbage collection (GC)**:
- GC quyết định khả năng thu hồi memory dựa trên **reachability** và các quy tắc runtime.
- `whole = null` chỉ thay đổi một reference variable; chưa chắc object whole không còn reference khác.
- Part có thể còn được tham chiếu từ một object khác nếu API đã làm lộ reference.
- Không có bảo đảm thời điểm GC sẽ thực thi/thu hồi memory sau một phép gán null.
- `finalize()` không phải cách thiết kế vòng đời đáng tin cho ứng dụng Java hiện đại.

### Mô hình đúng hơn

**Domain lifecycle:**

```text
Order "cancelled"
  -> các OrderLine không còn hợp lệ như line của order đó.
```

**Memory lifecycle:**

```text
Một object không còn reachable từ GC roots
  -> đủ điều kiện để bộ thu gom xử lý theo quy tắc JVM,
     thời điểm không xác định bằng mã business đơn giản.
```

**Resource lifecycle:**

```text
Một owner đóng connection/stream/file
  -> gọi close() theo hợp đồng,
     không chờ GC để giải phóng resource đúng hạn.
```

Phân biệt ba tầng này giúp tránh nhầm composition với chuyện `System.gc()` hoặc tưởng rằng Java có destructor giống C++.

## 19. Sở hữu tài nguyên: `AutoCloseable` và try-with-resources

Đối tượng giữ tài nguyên bên ngoài JVM heap (file descriptor, socket, database connection, stream) cần **hợp đồng đóng tài nguyên**.

Nếu một object **tạo và sở hữu** một resource, object ấy thường chịu trách nhiệm gọi `close()`. Nếu object chỉ **mượn** resource, nó không nên đóng resource của caller trừ khi có thỏa thuận.

### Owner đóng resource của mình

```java
class ResourceOwner implements AutoCloseable {
    private final SomeCloseable resource;

    ResourceOwner() {
        resource = new SomeCloseable();
    }

    @Override
    public void close() throws Exception {
        resource.close();
    }
}
```

Đây là **mã minh họa**, vì `SomeCloseable` chưa được khai báo. Chương trình runnable dưới đây dùng class giả lập resource để quan sát vòng đời.

### Ví dụ Java 17 hoàn chỉnh

Lưu **`ResourceOwnershipDemo.java`**:

```java
final class Connection implements AutoCloseable {
    private boolean closed;

    void query() {
        if (closed) {
            throw new IllegalStateException("Connection closed");
        }
        System.out.println("query");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("connection closed");
        }
    }
}

final class ConnectionSession implements AutoCloseable {
    private final Connection connection = new Connection();

    void run() {
        connection.query();
    }

    @Override
    public void close() {
        connection.close();
    }
}

public class ResourceOwnershipDemo {
    public static void main(String[] args) {
        try (ConnectionSession session = new ConnectionSession()) {
            session.run();
        }

        System.out.println("done");
    }
}
```

```bash
javac -encoding UTF-8 ResourceOwnershipDemo.java
java ResourceOwnershipDemo
```

**Stdout:**

```text
query
connection closed
done
```

`ConnectionSession` **tạo và sở hữu** `Connection`, nên `ConnectionSession.close()` gọi `connection.close()`. `try-with-resources` bảo đảm gọi `session.close()` theo quy tắc khi kết thúc scope, kể cả khi thân try ném exception (các exception có thể được gắn dạng suppressed theo cơ chế Java).

**Đây là composition theo vòng đời tài nguyên**, không phải GC tự đóng connection.

### Tránh đóng resource được mượn

Nếu method nhận:

```java
void write(OutputStream borrowed, byte[] data) throws IOException {
    borrowed.write(data);
}
```

thì thông thường **caller sở hữu** `borrowed`. Method `write` chỉ **sử dụng** stream; đóng nó ở đây có thể khiến caller không tiếp tục dùng được. Nếu muốn method tiếp nhận ownership, tên method/tài liệu/API cần nêu **chuyển giao trách nhiệm close** rõ ràng.

## 20. Transfer ownership và borrowed reference

Hai hợp đồng khác nhau nhưng cùng chữ ký Java:

```java
void register(Resource resource);
```

Nó có thể có một trong hai ý nghĩa:

1. **Borrowed:** service chỉ dùng resource, không đóng, không giữ sau khi gọi.
2. **Ownership transfer:** sau `register`, service chịu trách nhiệm quản lý/đóng resource; caller không nên tiếp tục thao tác làm sai invariant.

Java compiler **không suy luận** sự khác biệt này từ tham số `Resource`.

### Viết contract rõ ràng

Ví dụ mô tả API:

```text
registerOwned(resource):
  Nếu thành công, registry nhận trách nhiệm close resource.
  Caller không được close resource khi registry còn sở hữu.

inspect(resource):
  Chỉ đọc trong thời gian gọi; caller vẫn giữ ownership.
  Method không lưu reference và không close resource.
```

Đây là hướng dẫn hợp đồng, không phải cú pháp Java.

Nếu ứng dụng cần strict guarantees, có thể dùng một **wrapper đã chuyển trạng thái**, kiểm tra `closed/transferred`, hoặc cung cấp interface giới hạn quyền truy cập. Cần nhớ alias ngoài vẫn có thể tồn tại nếu caller giữ reference và kiểu Java cho phép thao tác.

## 21. Không phải mọi “has-a” đều là composition

Câu `Car has an Engine` chưa đủ để phân loại:

**Trường hợp A: Engine được car sở hữu riêng**

```java
class Car {
    private final Engine engine = new Engine();
}
```

Nếu Engine không được lộ, được Car tạo/quản lý và gắn với vòng đời Car theo contract, đây có thể là **composition**.

**Trường hợp B: Car dùng Engine do caller cung cấp**

```java
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }
}
```

Trường hợp này có **association** chắc chắn, nhưng **chưa đủ thông tin** để kết luận ownership. Caller có thể sở hữu Engine, hoặc có thể chuyển giao quyền sở hữu cho Car; contract quyết định.

**Trường hợp C: Car chỉ mượn Engine để kiểm tra**

```java
class Diagnostics {
    void inspect(Engine engine) {
        engine.selfTest();
    }
}
```

Nếu không giữ reference, quan hệ là **uses/dependency** tại mức đang xét.

Thường cần hỏi tiếp: “Engine có thể thay owner? Có thể dùng chung? Ai phải close? API có trả Engine ra không?” trước khi vẽ hình thoi đặc.

## 22. Composition và immutable value object

Những part mang dữ liệu bất biến thường dễ kiểm soát hơn. Ví dụ:

```java
record Coordinates(double latitude, double longitude) {
}

final class Location {
    private final Coordinates point;

    Location(double latitude, double longitude) {
        point = new Coordinates(latitude, longitude);
    }

    Coordinates point() {
        return point;
    }
}
```

`Coordinates` là immutable về mặt state của hai primitive components theo API record thông thường; việc chia sẻ reference `point` không cho caller sửa latitude/longitude sau khi khởi tạo.

Nhưng **không phải record nào cũng sâu bất biến**:

```java
record MutableBox(int[] values) {
}
```

`MutableBox` giữ một mảng có thể thay đổi. Nếu muốn bảo vệ ownership, cần copy mảng ở constructor/accessor hoặc chuyển sang immutable representation.

### Bài học

Composition không đòi hỏi mọi part đều mutable hay phải che giấu hoàn toàn value objects. Một **immutable value object** có thể được chia sẻ an toàn về mặt mutation dù ownership domain vẫn phải được xác định đúng.

## 23. Constructor injection: dependency hay association?

Ví dụ:

```java
interface MessageSender {
    void send(String message);
}

final class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }

    void notifyUser(String text) {
        sender.send(text);
    }
}
```

`NotificationService` **phụ thuộc** vào abstraction `MessageSender` và đồng thời **giữ association** tới một sender instance.

**Dependency Injection (DI)** thường là cơ chế **cung cấp dependency**, chứ không tự phân loại aggregation hay composition.

Nếu `sender` do container DI tạo và quản lý, `NotificationService` có thể **mượn** sender. Nếu `NotificationService` trực tiếp tạo sender và nhận trách nhiệm đóng nó, ownership lại khác.

Vì vậy:
- **Constructor injection**: nói về cách truyền dependency khi xây object.
- **Association**: nói về quan hệ giữ tham chiếu của các objects.
- **Ownership**: nói về trách nhiệm vòng đời/mutation/resource.

Ba điều có thể đồng thời đúng ở các mức khác nhau.

## 24. Ví dụ DI bằng interface và association dài hạn

Lưu **`ConstructorInjectionDemo.java`**:

```java
interface MessageSender {
    void send(String message);
}

final class ConsoleSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("SEND: " + message);
    }
}

final class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }

    void welcome(String name) {
        sender.send("Xin chào " + name);
    }
}

public class ConstructorInjectionDemo {
    public static void main(String[] args) {
        MessageSender sharedSender = new ConsoleSender();

        NotificationService first =
                new NotificationService(sharedSender);
        NotificationService second =
                new NotificationService(sharedSender);

        first.welcome("An");
        second.welcome("Bình");
    }
}
```

```bash
javac -encoding UTF-8 ConstructorInjectionDemo.java
java ConstructorInjectionDemo
```

Stdout:

```text
SEND: Xin chào An
SEND: Xin chào Bình
```

Hai services chia sẻ **cùng object sender**. Có association qua field và dependency tới interface. Nhưng không có chuyện mỗi service sở hữu độc quyền sender; caller/container có thể quản lý vòng đời `sharedSender`.

### Ưu điểm thiết kế

- Phụ thuộc vào **interface** thay vì implementation cụ thể.
- Có thể thay bằng test double/mock sender để unit test.
- Vòng đời sender có thể do outer layer/container quản lý.
- Tránh tự `new ConsoleSender()` sâu trong service khi caller cần quyền cấu hình.

Tuy vậy DI không bắt buộc cho mọi class; với một immutable value object đơn giản, constructor trực tiếp có thể đủ.

## 25. Association trong collection: 1–nhiều và nhiều–nhiều

Một `University` có thể quản lý nhiều `Course`:

```java
class University {
    private final List<Course> courses = new ArrayList<>();
}
```

Đây là ứng viên cho association `University 1 -> 0..* Course`, nhưng cần hỏi:
- Một Course có thuộc đúng một University không?
- Course có được chuyển University?
- Course có tồn tại độc lập ngoài University?
- University có chịu trách nhiệm xóa Course không?
- List có được lộ ra ngoài để client xóa Course tùy ý không?

Nếu Course là domain entity độc lập, có thể chọn association/aggregation. Nếu một cấu trúc phụ thuộc chặt vào University và không tồn tại ngoài, composition có thể phù hợp.

### Many-to-many trong code

Trong domain, `Student` và `Course` có thể quan hệ nhiều-nhiều:
- Một Student học nhiều Courses.
- Một Course có nhiều Students.

Không nhất thiết phải lưu hai mutable collections trực tiếp trong Student và Course. Có thể dùng **Enrollment** object làm entity liên kết, chứa metadata như ngày đăng ký/điểm:

```java
record Enrollment(String studentId, String courseId, int year) {
}
```

Trong hệ thống có database, quan hệ many-to-many thường được quản lý bằng bảng join/aggregate riêng. Đây là vấn đề domain/data modeling, không phải dấu hiệu tự động của composition.

## 26. Quan hệ qua ID khác quan hệ qua object reference

Hai thiết kế:

```java
class Order {
    private Customer customer;
}
```

và:

```java
class Order {
    private String customerId;
}
```

Trong thiết kế thứ nhất, Order giữ **object reference** (association trực tiếp trong memory).

Trong thiết kế thứ hai, Order giữ **identifier** để tra Customer khi cần. Ở mức domain, vẫn có quan hệ Order–Customer, nhưng trong Java object graph chưa chắc có tham chiếu trực tiếp tới Customer.

Điều này quan trọng với:
- Persisted entities;
- Microservices và remote boundaries;
- Serialization;
- Lazy loading;
- Tránh vòng tham chiếu;
- Giảm coupling giữa aggregates.

**Đừng vẽ UML dựa hoàn toàn vào việc có field kiểu `Customer` hay `String`.** Quan hệ nghiệp vụ có thể được biểu diễn gián tiếp bằng ID hoặc query.

## 27. Aggregates và aggregate root: không đồng nghĩa UML aggregation

Trong Domain-Driven Design (DDD), **aggregate** là ranh giới nhất quán của một tập domain objects và **aggregate root** là entry point để thay đổi chúng theo invariant.

Thuật ngữ DDD **aggregate** không có nghĩa trùng hoàn toàn với **shared aggregation (hình thoi rỗng) trong UML**.

Ví dụ `Order` có thể là **aggregate root**; `OrderLine` được chỉnh qua `Order.addLine`/`Order.removeLine`. Điều này gần với composition trong thiết kế, nhưng cần tách:
- Ranh giới transaction/invariant của DDD aggregate;
- UML whole–part semantics;
- Java object references và memory lifecycle.

Một aggregate root có thể tham chiếu một entity thuộc aggregate khác bằng **ID**, không có nghĩa nó sở hữu toàn bộ vòng đời entity đó.

### Quy tắc thực hành

Nếu một child không được phép bị cập nhật mà bỏ qua validation của owner, **đừng trả mutable child hoặc backing collection** cho caller tùy ý sửa. Hãy cung cấp command method ở owner và các read models/snapshots phù hợp.

## 28. Shared mutable objects và quyền cập nhật

Một aggregation thường tạo cơ hội **chia sẻ part** qua nhiều owners/whole objects.

Ví dụ một `Employee` có thể xuất hiện trong nhiều `Team`. Nếu Employee mutable, việc `employee.rename(...)` ở một nơi có thể làm tất cả các Team quan sát tên mới.

Đó có thể là **hành vi mong muốn**, nhưng phải được nêu rõ:
- Mỗi Team dùng identity Employee chung hay snapshot?
- Ai được quyền chỉnh Employee?
- Có cần event/notification khi Employee đổi?
- Nếu nhiều thread, ai đồng bộ?

Trong composition, một cách tránh alias là:
- Tạo part bên trong owner;
- Không trả part mutable trực tiếp;
- Dùng value objects immutable;
- Copy đầu vào mutable;
- Mở API thay đổi qua owner.

**Không phải mọi chia sẻ đều sai.** Sai chủ yếu khi object bị thay đổi **ngoài contract/invariant mong muốn**.

## 29. Cycle của object graph và rủi ro khi serialize

Association hai chiều dễ tạo graph:

```text
A -> B -> A
```

Ví dụ:

```java
class Parent {
    Child child;
}

class Child {
    Parent parent;
}
```

Nếu dùng serializer tự đệ quy các field mà không quản lý identity/cycle, có thể dẫn đến lặp vô hạn hoặc lỗi stack.

Trong Java GC hiện đại, **cycle tự thân không ngăn garbage collection** khi toàn bộ cycle không còn reachable từ GC roots; không cần phá mỗi reference cycle chỉ để Java heap GC làm việc.

Tuy nhiên vẫn cần chú ý:
- Serialization theo JSON có thể cần identity references/DTO mapping hoặc bỏ back-reference.
- `toString()` của A gọi `B.toString()` và ngược lại có thể gây recursion.
- `equals`/`hashCode` duyệt graph hai chiều có thể gây recursion hoặc quá tốn kém.
- UI/data binding có thể cần tránh tự lặp qua object graph.

### Giảm coupling

Một chiều association thường đơn giản hơn nếu nghiệp vụ không cần truy ngược. Đừng tạo back-reference chỉ vì muốn “đủ hai chiều trên UML”.

## 30. Không đồng nhất strong/weak references với aggregation/composition

Java có API tham chiếu như `java.lang.ref.WeakReference`, nhưng nó **không phải** cách trực tiếp mã hóa UML shared aggregation.

- **Strong reference**: hình thức tham chiếu thông thường, ảnh hưởng reachability theo cơ chế JVM.
- **WeakReference**: tham chiếu đặc biệt có thể không giữ object sống trước GC theo cùng cách với strong reference.
- **Aggregation/composition**: mô tả **ngữ nghĩa quan hệ domain và ownership**.

Dùng `WeakReference` không tự làm một quan hệ thành UML aggregation. Cũng không phải composition luôn cần strong reference suốt đời chương trình.

Chỉ cân nhắc weak/soft/phantom references theo bài toán cache, canonical mapping hoặc quản lý lifecycle đặc biệt đã hiểu rõ, không dùng chúng như bản dịch máy móc của hình thoi UML.

## 31. Đọc ký hiệu UML cơ bản

Thường thấy:

```text
A  - - - - > B        Dependency (nét đứt)
A  -------- B         Association (nét liền)
Whole ◇----- Part     Shared aggregation (hình thoi rỗng ở Whole)
Whole ◆----- Part     Composition (hình thoi đặc ở Whole)
Child ------▷ Parent  Generalization/inheritance (tam giác rỗng về Parent)
```

Hướng arrow, role name, multiplicity và navigability có những quy tắc trình bày riêng. Ở đây chỉ dùng **ASCII gần đúng** để nhận diện; khi vẽ UML chính thức, chọn đúng loại đầu mũi tên/hình thoi.

### Điểm đáng nhớ khi đọc diamond

**Hình thoi đặt ở phía whole/owner**, không đặt phía part.

Ví dụ:

```text
Order ◆-------- OrderLine
 1                 1..*
```

Ý nghĩa gần đúng: một Order gồm một hoặc nhiều lines (nếu domain yêu cầu tối thiểu một); mỗi line thuộc một Order composite tại một thời điểm theo semantics UML.

Java không tự ngăn Order có zero lines. Nếu diagram ghi `1..*` thì API/order lifecycle phải bảo đảm invariant đó theo mô hình — ví dụ không cho order hoàn tất nếu rỗng.

## 32. Cách chuyển UML thành thiết kế Java

Một quy trình hữu ích:

1. **Xác định object identities**: các thực thể có vòng đời riêng hay chỉ là giá trị?
2. **Xác định hướng truy cập**: ai cần biết ai?
3. **Xác định multiplicity**: `1`, `0..1`, `0..*` hay `1..*`?
4. **Xác định ownership**: ai tạo, ai giữ, ai sửa, ai kết thúc vòng đời?
5. **Chọn API**: tham số method, constructor injection, field, collection, ID hay repository query?
6. **Khóa invariants**: non-null, uniqueness, no duplicate ownership, consistency hai chiều.
7. **Kiểm soát alias**: có trả mutable internals không, có nhận mutable input trực tiếp không?
8. **Quản lý resource**: owner có cần `AutoCloseable`/`close` không?
9. **Đánh giá concurrency** nếu object graph được chia sẻ.
10. **Viết tests** cho di chuyển association, shared parts, xóa composite, snapshot, đóng resource.

### Không vẽ class diagram từ code một cách máy móc

Một static helper gọi method trên object nhận tham số không nhất thiết là structural association. Một collection field không chứng minh composition. Một Java class có thể bao gồm cả **dependency tới abstraction** và **association tới instance** cùng lúc.

Mục tiêu của diagram là truyền đạt **quan hệ có ý nghĩa với người đọc**, không phải sao chép mọi biến local.

## 33. Phân biệt inheritance, composition và delegation

**Inheritance:** `extends`; subtype quan hệ is-a.

**Composition:** object chủ quản chứa/quản lý một hoặc nhiều object thành phần; tập trung whole–part ownership.

**Delegation:** object A nhận lời gọi rồi ủy quyền công việc cho object B, bất kể B được sở hữu hay mượn.

Ví dụ:

```java
final class PrinterService {
    private final Printer printer;

    PrinterService(Printer printer) {
        this.printer = printer;
    }

    void print(String text) {
        printer.print(text);
    }
}
```

`PrinterService` **delegates** việc in cho `Printer`. Nó **liên kết** tới Printer qua field. Nhưng nó **không nhất thiết sở hữu vòng đời Printer** — nếu printer được DI container cung cấp, service thường chỉ mượn instance.

Vì vậy “delegation” không đồng nghĩa “composition”, dù chúng có thể cùng xuất hiện trong một thiết kế.

## 34. Composition over inheritance: hiểu đúng lời khuyên

Câu “prefer composition over inheritance” thường khuyên dùng các object cộng tác để cấu thành hành vi thay vì lạm dụng hierarchy subclass.

Ví dụ thay vì:

```java
class SpecialReport extends BaseReport {
    // Override rất nhiều bước để thay formatter.
}
```

có thể dùng:

```java
final class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = formatter;
    }
}
```

Đây là **object composition/delegation** theo cách nói phổ biến trong design patterns, nhưng theo UML lifecycle semantics, `ReportService` có thể chỉ **association** với Formatter được chia sẻ qua DI. Thuật ngữ “composition” trong lời khuyên thiết kế **không phải lúc nào** cũng chỉ hình thoi đặc UML.

### Khi inheritance vẫn đúng

Inheritance có thể phù hợp khi:
- Subtype tuân thủ contract của supertype;
- Framework có extension points có chủ đích;
- Polymorphism qua class hierarchy mang ý nghĩa domain thực;
- Không phải chỉ vì muốn tái sử dụng vài dòng code.

Association/composition thường phù hợp hơn khi A **có** B hoặc **dùng** B, không phải A **là một** B.

## 35. Chọn interface ở ranh giới dependency

Giả sử `CheckoutService` cần tính thuế. Việc phụ thuộc trực tiếp:

```java
class CheckoutService {
    private final FixedTaxCalculator calculator =
            new FixedTaxCalculator();
}
```

làm service chọn implementation ngay trong chính nó.

Có thể dùng abstraction:

```java
interface TaxCalculator {
    long tax(long subtotal);
}

final class CheckoutService {
    private final TaxCalculator calculator;

    CheckoutService(TaxCalculator calculator) {
        this.calculator = calculator;
    }
}
```

Lợi ích:
- Dễ thay quy tắc tính thuế mà không sửa core service.
- Dễ test bằng implementation đơn giản.
- Vòng đời TaxCalculator có thể được owner phía trên quản lý.
- Service phụ thuộc vào **contract**, không phải class cụ thể.

Nhưng interface không giải quyết tự động:
- Ai sở hữu calculator?
- Calculator có mutable state không?
- Calculator có thread-safe khi dùng chung không?
- Service có được đóng calculator không?

**Dependency inversion và object ownership là hai câu hỏi riêng.**

## 36. Ví dụ service sử dụng và giữ cùng abstraction

Lưu **`StrategyAssociationDemo.java`**:

```java
interface Discount {
    int apply(int price);
}

final class FixedDiscount implements Discount {
    private final int amount;

    FixedDiscount(int amount) {
        this.amount = amount;
    }

    @Override
    public int apply(int price) {
        return Math.max(0, price - amount);
    }
}

final class Checkout {
    private final Discount discount;

    Checkout(Discount discount) {
        this.discount = java.util.Objects.requireNonNull(discount);
    }

    int calculate(int price) {
        return discount.apply(price);
    }
}

public class StrategyAssociationDemo {
    public static void main(String[] args) {
        Discount promotion = new FixedDiscount(20);

        Checkout first = new Checkout(promotion);
        Checkout second = new Checkout(promotion);

        System.out.println(first.calculate(100));
        System.out.println(second.calculate(15));
    }
}
```

```bash
javac -encoding UTF-8 StrategyAssociationDemo.java
java StrategyAssociationDemo
```

Stdout:

```text
80
0
```

Hai `Checkout` objects cùng liên kết tới một `Discount` object. Mỗi `calculate` dùng object này. Đây là **association với strategy** cùng **dependency vào interface**, không chứng minh rằng mỗi checkout sở hữu một Discount duy nhất.

## 37. Khi nào dùng một nguồn sự thật thay vì back-references?

Association hai chiều làm tăng nguy cơ **mất nhất quán**:

```text
Department.employees chứa An
Employee.department lại là QA
```

Nếu hệ thống không cần truy cập trực tiếp từ Employee về Department, có thể giữ duy nhất `Department.employees`.

Nếu cần truy vấn hai chiều nhưng dữ liệu nằm trong database, repository có thể trả `Department` của một Employee bằng query theo ID thay vì giữ hai reference mutable đồng thời trong heap.

Đánh đổi:
- **Một chiều**: ít invariant, dễ bảo trì, có thể cần query.
- **Hai chiều**: điều hướng thuận tiện hơn, nhưng phải cập nhật nguyên tử/đồng bộ trên hai phía.
- **Theo ID**: tách object graph, phù hợp bounded contexts/serialization, cần cơ chế resolve ID.

Không có mặc định “association đúng phải hai chiều”. Chỉ tạo back-reference nếu use case thực sự yêu cầu.

## 38. Thread-safety của shared aggregation

Trong shared aggregation, một `Member` hoặc `Formatter` có thể được dùng bởi nhiều owners/consumers.

Nếu shared object **immutable**, việc chia sẻ thường đơn giản hơn về mutation.

Nếu shared object **mutable**:
- Nhiều clients có thể cập nhật state chồng nhau.
- Thread khác có thể quan sát state thiếu đồng bộ.
- Một service có thể vô tình “đóng” resource mà service khác vẫn cần.
- Collection membership có thể thay đổi trong lúc duyệt.

Các giải pháp tùy domain:
- Immutable value object/snapshot;
- Synchronization;
- Concurrent collections;
- Ownership ràng buộc một thread;
- Event-driven model;
- Copy-on-write trong trường hợp phù hợp.

**`final` trên field reference không làm object chia sẻ thread-safe.**

Ví dụ `private final List<String> items = new ArrayList<>();` chỉ khóa phép gán lại field; việc nhiều thread thêm/xóa trên `ArrayList` vẫn cần bảo vệ.

## 39. Lifecycle test: kiểm tra ownership bằng hành vi

Đừng chỉ xem diagram đẹp. Hãy đặt các test/tình huống:

**Dependency:**
- Có thể truyền hai formatter khác nhau vào cùng một service?
- Sau lời gọi, service có cần giữ formatter không?

**Association:**
- Chuyển một Employee sang Department khác có cập nhật mọi phía?
- Hai Course có thể dùng cùng Instructor mà không tạo bản sao không?
- Nếu Instructor thay đổi tên, Courses có nên thấy giá trị mới?

**Aggregation:**
- Part có tồn tại độc lập sau khi whole không còn được dùng?
- Part có được chia sẻ giữa nhiều whole theo hợp đồng?
- Whole có được phép đóng/xóa part mà service khác đang dùng không?

**Composition:**
- Caller có được giữ mutable reference đến part và sửa ngoài owner không?
- Owner có validate invariant mỗi lần thêm/xóa part không?
- Đóng owner có đóng resource thực sự do owner sở hữu?
- Part có còn mang ý nghĩa nghiệp vụ hợp lệ sau khi owner kết thúc vòng đời không?

Các test này giúp kiểm tra **ngữ nghĩa**, thay vì suy đoán chỉ dựa vào `private final`.

## 40. Lỗi thường gặp

| Quan niệm / thiết kế sai | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| “Có field `B` là composition” | Field chỉ là reference | Xác định domain ownership và vòng đời |
| “Có `new B()` là chắc chắn composition” | B có thể bị trả ra và chia sẻ tùy ý | Xem hợp đồng, alias và responsibility |
| “Composition nghĩa GC xóa part ngay khi whole null” | GC không có thời điểm xác định | Tách domain lifecycle, GC và resource close |
| “Aggregation luôn được Java enforce bằng List” | Java không có aggregation keyword | Enforce invariant qua API |
| “Dependency bắt buộc phải là field” | Có thể là tham số/biến local | Mô hình uses theo phạm vi dùng |
| “Association chỉ có một chiều” | Có thể unidirectional hoặc bidirectional | Xác định navigability cần thiết |
| “Association hai chiều tự đồng bộ” | Hai references/collections dễ lệch | Tập trung thao tác quản lý liên kết |
| “List là quan hệ 1..*” | List có thể rỗng | Validate multiplicity |
| “`private final List` đồng nghĩa immutable” | List mutable vẫn được thay đổi | Dùng encapsulation, snapshot/immutable |
| “`List.copyOf` copy sâu objects” | Chỉ shallow copy elements | Bảo vệ mutable elements |
| “`Collections.unmodifiableList` là snapshot” | Đây thường là live view | Dùng snapshot nếu cần |
| “DI nghĩa service sở hữu dependency” | Container/caller có thể sở hữu | Nêu contract ownership/close |
| “Borrowed stream thì helper nên đóng cho an toàn” | Vi phạm vòng đời của caller | Chỉ owner đóng trừ khi transfer hợp lệ |
| “Hai Team dùng một Member là hai copies Member” | Cùng reference có thể được chia sẻ | Theo dõi object identity |
| “`extends` dùng được cho mọi has-a” | Is-a khác has-a | Dùng association/composition |
| “UML shared aggregation luôn có semantics rõ như composition” | Shared aggregation yếu/không thống nhất | Dùng association + ghi chú nếu cần |
| “Java reference cycle sẽ không được GC” | GC theo reachability, không phải reference counting đơn giản | Tách memory khỏi association |
| “Phải dùng WeakReference cho UML aggregation” | Weak reference có nghĩa runtime khác | Không dịch ký hiệu UML máy móc |
| “Một object không tham chiếu trực tiếp thì domain không có relation” | Có thể dùng ID/query | Phân biệt code graph và domain model |
| “Final class là immutable composite” | Final class cấm subclass, không cấm mutate state | Thiết kế immutable state riêng |
| “UML composition thay thế transaction consistency” | Diagram không tự triển khai invariant | Thiết kế API/transaction đồng bộ |
| “Mỗi part chỉ có một reference” | Composition ownership không đồng nghĩa chỉ có một Java reference tuyệt đối | Kiểm soát mutation/lifetime contract |

## 41. Bài tập có đáp án

### Bài 1 — Uses hay association?

```java
class InvoicePrinter {
    void print(Invoice invoice, Formatter formatter) {
        System.out.println(formatter.format(invoice.toString()));
    }
}
```

**Hỏi:** `InvoicePrinter` có giữ `Formatter` lâu dài không?

**Đáp án:** Không theo code được đưa ra. `Formatter` được truyền và dùng trong method; đây là **dependency (uses)** phù hợp. Nếu code thực sự lưu formatter vào field ở nơi khác, còn cần xét association.

### Bài 2 — Field có chắc là composition?

```java
class Course {
    private final Instructor instructor;

    Course(Instructor instructor) {
        this.instructor = instructor;
    }
}
```

**Đáp án:** Chưa đủ. Có association. Việc Instructor do caller đưa vào gợi ý quan hệ độc lập, nhưng không loại trừ ownership transfer theo hợp đồng; muốn kết luận composition/aggregation cần thêm semantics.

### Bài 3 — Chia sẻ part

```java
Member an = new Member("An");
teamA.add(an);
teamB.add(an);
```

**Đáp án:** Hai Team giữ cùng object `an`. Nếu Member có vòng đời độc lập, có thể mô tả aggregation/association chia sẻ theo domain. Không phải hai copies Member.

### Bài 4 — Order–Line

Order tự tạo mỗi line, line không có danh tính domain độc lập, mọi thay đổi phải qua Order, và xóa Order kéo theo kết thúc vòng đời các lines theo nghiệp vụ.

**Đáp án:** Đây là ứng viên điển hình cho **composition**. Tuy nhiên Java không tự enforce; API phải giữ đúng contract.

### Bài 5 — UML multiplicity

Diagram mô tả `Course 1 ---- 1 Instructor`. Khai báo `Instructor instructor;` đã đủ chưa?

**Đáp án:** Chưa. Biến có thể null. Cần validate trong constructor/update hoặc API/state machine bảo đảm một Instructor hợp lệ ở những trạng thái đòi hỏi.

### Bài 6 — Getter trả mutable list

```java
class Order {
    private final List<Line> lines = new ArrayList<>();

    List<Line> getLines() {
        return lines;
    }
}
```

**Đáp án:** Caller có thể `getLines().clear()` hoặc thêm phần tử không qua validation. Đây là representation exposure làm suy yếu ownership/invariant. Trả immutable snapshot/read model hoặc API chỉ đọc phù hợp.

### Bài 7 — Composition và GC

```java
Order order = new Order();
order = null;
```

**Đáp án:** Không thể kết luận Order và mọi parts đã lập tức bị JVM hủy. Có thể còn references khác; GC không có thời điểm thu hồi được bảo đảm. Lifecycle domain và memory GC khác nhau.

### Bài 8 — Borrowed resource

Method nhận một `OutputStream` do caller quản lý, chỉ cần ghi một lần.

**Đáp án:** Đây là dependency/borrowed use theo hợp đồng hợp lý. Không tự `close()` stream trong helper, trừ khi API nêu rõ method nhận ownership.

### Bài 9 — Constructor injection

`NotificationService` giữ field `MessageSender sender` nhận từ constructor, còn DI container quản lý sender.

**Đáp án:** Service có association tới sender instance và phụ thuộc vào `MessageSender` interface, nhưng **không nhất thiết sở hữu resource lifetime** của sender.

### Bài 10 — Bidirectional link

Employee chuyển từ DEV sang QA, nhưng `DEV.members` vẫn còn Employee.

**Đáp án:** Invariant association hai chiều bị sai. Cần thao tác chuyển quản lý cả tháo liên kết cũ, thêm liên kết mới, cập nhật Employee; trong nhiều thread cần transaction/synchronization phù hợp.

### Bài 11 — Aggregation và composition

Một `Library` quản lý nhiều `Book` vật lý. Khi thư viện ngừng hoạt động, sách có thể được chuyển sang thư viện khác; Book có ID và vòng đời độc lập.

**Đáp án:** Association/aggregation thường phản ánh yêu cầu này tốt hơn composition phụ thuộc vòng đời Library. Tuy nhiên mô hình phụ thuộc domain cụ thể, không chỉ tên class.

### Bài 12 — Composition với nested value object

`Order` có private nested record `Line(String sku,int count)`, tạo lines nội bộ và chỉ cung cấp `total()`.

**Đáp án:** Đây là thiết kế composition hợp lý: Order kiểm soát khởi tạo, invariant và không lộ mutable children. Record immutable theo các String/int components đơn giản giúp tránh alias mutation.

### Bài 13 — Cycle và GC

`A` tham chiếu `B`, `B` tham chiếu lại `A`. Không có GC roots nào reach được cả A lẫn B.

**Đáp án:** Reference cycle **không tự ngăn** Java garbage collector thu hồi chúng. Nhưng serializer/toString đệ quy vẫn có thể gặp recursion nếu không quản lý cycle.

### Bài 14 — Association qua ID

Order chỉ lưu `String customerId`, không lưu `Customer` object.

**Đáp án:** Vẫn có thể có relation Order–Customer ở domain/UML. Java object graph không bắt buộc có direct reference; hệ thống có thể resolve qua repository.

### Bài 15 — “Composition over inheritance”

`ReportService` có field `Formatter` injected và gọi `formatter.format(...)`. Đây có phải UML composition không?

**Đáp án:** Nó rõ ràng dùng **delegation** và có association tới formatter. Trong lời khuyên “composition over inheritance”, người ta nói tới kết hợp đối tượng thay vì subclassing; điều đó **không tự chứng minh strong ownership** theo nghĩa UML composition.

## 42. Checklist thiết kế quan hệ giữa các lớp

1. **Nêu rõ vai trò A/B:** ai là consumer, provider, whole, part?
2. **Xác định domain identity:** B có thể tồn tại như entity độc lập không?
3. **Kiểm tra uses-only:** A có chỉ dùng B trong method rồi thôi không?
4. **Kiểm tra association:** A có cần giữ link tới B trong state không?
5. **Nếu association hai chiều**, có cần thật không và ai duy trì invariant?
6. **Xác định multiplicity**: `1`, `0..1`, `0..*`, `1..*` và validation.
7. **Xác định navigability:** chỉ A→B hay cần B→A?
8. **Nếu whole–part**, part có được chia sẻ/di chuyển hay thuộc độc quyền whole?
9. **Nếu chọn aggregation**, ghi rõ lifetime independence; đừng dựa chỉ vào hình thoi rỗng.
10. **Nếu chọn composition**, mô tả ai tạo/chuyển ownership, ai mutate, ai kết thúc lifetime.
11. **Đừng đồng nhất field `private final` với ownership**.
12. **Kiểm tra aliasing:** input mutable còn bị caller giữ không? Getter có lộ state không?
13. **Dùng immutable value types/defensive copies** khi cần bảo vệ invariant.
14. **Nếu có resources**, xác định ai phải gọi `close()` và dùng `AutoCloseable` khi phù hợp.
15. **Nếu dùng DI**, xác định container/caller hay service sở hữu dependency.
16. **Nếu object được chia sẻ**, kiểm tra concurrency/thread-safety và không đóng tài nguyên sớm.
17. **Nếu model qua ID**, đảm bảo resolution/consistency theo hệ thống persistence.
18. **Nếu có cycles**, xem serializer, `toString`, `equals/hashCode` có xử lý an toàn không.
19. **Đừng dùng inheritance cho has-a/uses-a**; is-a phải thỏa behavioral contract.
20. **Viết test cho lifecycle**, chuyển membership, sharing, removal, snapshot và exception.
21. **Vẽ UML vừa đủ**, có nhãn role/multiplicity khi người đọc cần.
22. **Phân biệt DDD aggregate với UML shared aggregation**.
23. **Không dùng `WeakReference` làm dấu hiệu UML aggregation**.
24. **Xác nhận loại quan hệ bằng nghiệp vụ** thay vì chỉ suy đoán từ syntax Java.

## Ghi nhớ

- **Dependency (uses):** A cần B để thực hiện một thao tác, có thể chỉ thông qua tham số và không lưu reference.
- **Association:** A và B có liên kết cấu trúc, thường được thể hiện bằng field/collection hoặc quan hệ qua ID.
- **Aggregation:** whole–part chia sẻ, part có thể có vòng đời độc lập; UML hình thoi rỗng có semantics tương đối yếu và cần giải thích domain.
- **Composition:** whole–part sở hữu mạnh, part bị kiểm soát bởi owner về vòng đời/invariant; UML hình thoi đặc ở phía whole.
- **Java không có keyword cho aggregation/composition.** `private`, `final`, `new` hay `List<T>` không tự chứng minh quyền sở hữu.
- **Một object có thể có nhiều references**; aliasing, defensive copy và immutable values quyết định mức độ bảo vệ state trong thực tế.
- **GC không đồng nghĩa business deletion hoặc `close()`**. Đối với resource, hãy thiết kế trách nhiệm đóng rõ ràng.
- **Constructor injection** truyền dependency; nó không nhất thiết chuyển ownership resource sang service.
- **Inheritance (is-a) khác association/composition (has-a) và dependency (uses-a)**.
- Mô hình tốt nhất là mô hình thể hiện **identity, multiplicity, navigability, ownership và những invariant có thể kiểm thử** — không chỉ dùng đúng mũi tên UML.
