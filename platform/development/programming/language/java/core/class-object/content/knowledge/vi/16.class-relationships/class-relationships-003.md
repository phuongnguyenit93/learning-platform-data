# Quan hệ một–một và một–nhiều bằng trường tham chiếu trong Java

Trong chương trình hướng đối tượng, một đối tượng thường **biết** hoặc **chứa** những đối tượng khác. Ví dụ, một `User` có `Profile`, một `Department` có nhiều `Employee`, một `Order` chứa nhiều `OrderLine`. Java biểu diễn các liên kết đó bằng **trường tham chiếu (reference fields)** hoặc bằng một **collection chứa các tham chiếu**.

~~~java
class User {
    Profile profile;                     // Một reference.
}

class Department {
    java.util.List<Employee> employees; // Một reference tới List chứa nhiều references.
}
~~~

Đây là những khai báo minh họa, chưa đủ tạo quan hệ hợp lệ. Java **không có từ khóa `one-to-one` hoặc `one-to-many`**; tính duy nhất, số lượng tối thiểu/tối đa, quyền thay liên kết và tính nhất quán hai chiều là **ràng buộc nghiệp vụ do code phải bảo vệ**.

Bài học thuộc Java Core — **Class & Object / Quan hệ giữa lớp**, dùng Java 17+. Những chương trình hoàn chỉnh đi kèm tên file, lệnh `javac`/`java`, stdout; các đoạn code lẻ được ghi rõ là minh họa.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Hiểu kiểu tham chiếu, object identity và trường reference.
2. Phân biệt **một–một** với **một–nhiều** theo hướng điều hướng và cardinality.
3. Hiểu ký hiệu `0..1`, `1`, `0..*`, `1..*` và giới hạn tối đa.
4. Viết liên kết một chiều và hai chiều bằng fields, constructors, methods.
5. Biết một field đơn **không tự đảm bảo one-to-one uniqueness toàn hệ thống**.
6. Dùng `List`, `Set`, `Map` phù hợp khi liên kết nhiều object.
7. Quản lý liên kết ngược và chuyển đối tượng giữa hai owners.
8. Biết vì sao `private final List` chưa đủ để che giấu mutable state.
9. Phân biệt `==` với `equals/hashCode` trong duplicate checking.
10. Nhận biết association, aggregation, composition và không nhầm với `extends`.
11. Chọn null/`Optional` và constructor validation đúng khi liên kết tùy chọn hoặc bắt buộc.
12. Tránh recursion qua quan hệ hai chiều, memory retention, race condition và test phụ thuộc state.
13. Thiết kế API có nghĩa, bảo vệ các ràng buộc quan hệ và test các đường thất bại.

## 2. Reference field và object graph

Một trường kiểu object giữ **giá trị tham chiếu** hoặc `null`, không chứa một bản sao hoàn chỉnh của object đích:

~~~java
class Address {
    String city;
}
class Customer {
    Address address;
}
~~~

Nếu thực thi:

~~~java
Address a = new Address();   // Address #1.
Customer c = new Customer(); // Customer #1.
c.address = a;
a.city = "Hue";
~~~

ta có:

~~~text
c ----> Customer #1
             |
             | address
             v
          Address #1 <---- a
          city="Hue"
~~~

`c.address` và `a` cùng tham chiếu một Address object. Khi `a.city` đổi, `c.address.city` cũng quan sát cùng trạng thái. Phép gán `c.address = a` **không tạo Address thứ hai**.

Sơ đồ mũi tên chỉ là mô hình logic; nhãn #1 không phải địa chỉ máy mà Java cho phép thao tác trực tiếp.

### Field không tự tạo object

~~~java
class Customer {
    Address address;
}
~~~

Nếu constructor/initializer chưa gán, field reference `address` mặc định là `null`. Đọc `customer.address.city` khi address null ném `NullPointerException`. Phải dùng constructor, factory hoặc method để gán một reference hợp lệ.

## 3. Cardinality phải được mô tả ở hai phía

| Ký hiệu UML | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `0..1` | Có thể không có hoặc có một | Tài khoản có thể chưa có ảnh đại diện |
| `1` | Bắt buộc đúng một | Invoice phải có Customer |
| `0..*` | Không hoặc nhiều | Team có thể chưa có Member |
| `1..*` | Ít nhất một | Order đã chốt phải có ít nhất một Line |
| `0..5` | Từ không tới tối đa năm | Nhóm được nhận tối đa 5 thành viên |

Quan hệ có **hai đầu**. Ví dụ:

~~~text
Department 1 -------- 0..* Employee
Employee   0..1 ----- 1 Department
~~~

Nội dung mô hình: một Department có thể quản lý nhiều Employees; một Employee có thể chưa thuộc hoặc thuộc một Department. Một employee **không được** đồng thời thuộc hai departments nếu hợp đồng chỉ cho `0..1`.

### Điều Java không tự thực thi

- `Profile profile;` không đảm bảo một Profile không được hai Users cùng giữ.
- `List<Employee> employees;` không tự chặn duplicates.
- `final` không buộc một relation tồn tại hoặc unique.
- Quan hệ hai chiều không tự đồng bộ các fields.
- Java core không có “foreign key” tự bảo đảm consistency giữa objects; database/ORM có cơ chế riêng.

Hãy viết **invariant** trước khi quyết định cách lưu reference.

## 4. Một–một một chiều

Một liên kết **một chiều** chỉ cho điều hướng từ A sang B:

~~~text
User --------> Profile
~~~

Nếu Profile không cần biết User, đây là thiết kế đơn giản. Khi Profile bắt buộc tồn tại và không được thay sau tạo, một `private final Profile` với constructor validation rất rõ.

Tạo **`UnidirectionalOneToOneDemo.java`**:

~~~java
import java.util.Objects;

public class UnidirectionalOneToOneDemo {
    record Profile(String name, String language) {
        Profile {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            if (language == null || language.isBlank()) {
                throw new IllegalArgumentException("language required");
            }
        }
    }

    static final class User {
        private final String id;
        private final Profile profile;

        User(String id, Profile profile) {
            this.id = Objects.requireNonNull(id, "id");
            this.profile = Objects.requireNonNull(profile, "profile");
        }

        String description() {
            return id + ": " + profile.name()
                    + " (" + profile.language() + ")";
        }

        Profile profile() {
            return profile;
        }
    }

    public static void main(String[] args) {
        Profile p = new Profile("Mai", "vi");
        User u = new User("U1", p);
        System.out.println(u.description());
        System.out.println("same=" + (u.profile() == p));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnidirectionalOneToOneDemo.java
java UnidirectionalOneToOneDemo
~~~

Stdout:

~~~text
U1: Mai (vi)
same=true
~~~

**Diễn giải:** `User` giữ reference tới cùng Profile mà caller đã tạo. `Profile` chỉ có String components nên có trạng thái bất biến theo contract thông thường. Field `final` không được gán lại ở User sau constructor.

**Giới hạn:** Nếu tạo `new User("U2", p)`, Java vẫn chấp nhận và hai Users cùng trỏ Profile p. Đây là **một reference cho mỗi User**, chưa phải **uniqueness một–một nghiêm ngặt ở cả hai phía**.

## 5. Tùy chọn một–một: `0..1`

Với liên kết tùy chọn, field có thể null:

~~~java
class Account {
    private Contact contact;

    java.util.Optional<Contact> contact() {
        return java.util.Optional.ofNullable(contact);
    }
}
~~~

Đây là mảnh minh họa với class `Contact` cần được định nghĩa. `Optional` ở **return type** thể hiện rõ khả năng không có liên kết; không buộc caller tự đoán null.

Tạo **`OptionalRelationDemo.java`**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class OptionalRelationDemo {
    record Contact(String phone) {}

    static final class Account {
        private Contact contact;

        void attach(Contact value) {
            contact = Objects.requireNonNull(value);
        }

        void detach() {
            contact = null;
        }

        Optional<Contact> contact() {
            return Optional.ofNullable(contact);
        }
    }

    public static void main(String[] args) {
        Account a = new Account();
        System.out.println("before=" +
                a.contact().map(Contact::phone).orElse("none"));

        a.attach(new Contact("0123"));
        System.out.println("after=" +
                a.contact().map(Contact::phone).orElse("none"));

        a.detach();
        System.out.println("removed=" + a.contact().isEmpty());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OptionalRelationDemo.java
java OptionalRelationDemo
~~~

Stdout:

~~~text
before=none
after=0123
removed=true
~~~

Với **bắt buộc `1`**, tốt hơn là dùng constructor non-null và không có method detach nếu invariant phải luôn đúng. Với **`0..1`**, null có thể là trạng thái hợp lệ nhưng nên có semantics và API rõ.

## 6. Một–một hai chiều và tính toàn vẹn

Nếu cả Person và Passport cần điều hướng tới nhau:

~~~text
Person #1 ----passport----> Passport #1
   ^                            |
   |----------holder------------+
~~~

Invariant:

~~~text
person.passport == passport
passport.holder == person
~~~

Nếu chỉ thực hiện `person.passport = passport`, Java không tự gán `passport.holder`. Nếu một Person thứ hai liên kết cùng Passport mà không kiểm tra, uniqueness bị phá. Vì vậy cần **một operation quản lý cả hai phía**.

### Ví dụ chạy: độc quyền ở mức object

Tạo **`BidirectionalOneToOneDemo.java`**:

~~~java
import java.util.Objects;

public class BidirectionalOneToOneDemo {
    static final class Passport {
        private final String number;
        private Person holder;

        Passport(String number) {
            this.number = Objects.requireNonNull(number);
        }

        void claim(Person person) {
            Objects.requireNonNull(person);
            if (holder != null && holder != person) {
                throw new IllegalStateException("already assigned");
            }
            holder = person;
        }

        String holderName() {
            return holder == null ? "none" : holder.name();
        }

        String number() {
            return number;
        }
    }

    static final class Person {
        private final String name;
        private Passport passport;

        Person(String name) {
            this.name = Objects.requireNonNull(name);
        }

        void attach(Passport target) {
            Objects.requireNonNull(target);
            if (passport != null) {
                throw new IllegalStateException("person already linked");
            }
            target.claim(this);
            passport = target;
        }

        String name() {
            return name;
        }

        String passportNumber() {
            return passport == null ? "none" : passport.number();
        }
    }

    public static void main(String[] args) {
        Person mai = new Person("Mai");
        Person an = new Person("An");
        Passport p = new Passport("P01");

        mai.attach(p);
        System.out.println("Mai=" + mai.passportNumber());
        System.out.println("holder=" + p.holderName());

        try {
            an.attach(p);
        } catch (IllegalStateException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("An=" + an.passportNumber());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BidirectionalOneToOneDemo.java
java BidirectionalOneToOneDemo
~~~

Stdout:

~~~text
Mai=P01
holder=Mai
rejected=already assigned
An=none
~~~

`Passport.claim` kiểm tra trước khi cập nhật reference. Nếu Passport đã có holder khác, nó ném exception, vì vậy `Person.attach` không gán Passport vào An. Cả hai hướng còn nhất quán trong tình huống tuần tự của demo.

**Giới hạn:** Ví dụ chưa hỗ trợ unlink/replacement và chưa đồng bộ giữa threads. Việc unique chỉ được bảo vệ qua API đã xây dựng trong runtime hiện tại; nếu dùng DB, cần thêm constraint/transaction. Nested classes trong cùng outer class dễ trình bày cùng file; access giữa các lớp thực tế cần API/helper permissions được thiết kế phù hợp.

## 7. Có nên luôn tạo liên kết ngược?

Không. **Unidirectional** đơn giản, ít state phải đồng bộ. **Bidirectional** cho phép điều hướng nhanh từ cả hai phía nhưng tăng coupling:

- Phải cập nhật cả hai khi attach/detach/replace.
- Dễ có cycle làm `toString` hoặc serialization đệ quy.
- Dễ có rò rỉ tham chiếu nếu registry giữ object ở cả hai phía.
- Cần lựa chọn một owner có trách nhiệm cập nhật invariant.

Chỉ dùng backreference khi có **use case thực**: ví dụ Employee cần biết Department của mình, hoặc một entity cần tham chiếu ngược để kiểm tra domain rule.

## 8. Một–nhiều: một field tới collection

Ví dụ:

~~~java
class Team {
    private final java.util.List<Member> members =
            new java.util.ArrayList<>();
}
~~~

Có ba cấp object:

~~~text
Team #1
   |
   | members field
   v
List #1 [0] -------------> Member #1
        [1] -------------> Member #2
        [2] -------------> Member #3
~~~

Field `members` giữ reference tới **List object**. List lưu các reference values tới **Member objects**. List không tự tạo các Members, và `members.add(existing)` không clone existing.

### Những ràng buộc phải xác định

- Team có thể rỗng không (`0..*` hay `1..*`)?
- Cho phép thêm cùng Member object hai lần không?
- Hai Members có cùng tên nhưng khác ID có hợp lệ không?
- Có giới hạn tối đa member count không?
- Caller có được thay trực tiếp collection không?
- Một Member có thể thuộc nhiều Teams không?

Một `List<Member>` không tự biết đáp án của những câu hỏi này.

## 9. Một–nhiều một chiều: Team → Members

Tạo **`OneToManyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OneToManyDemo {
    static final class Member {
        private final String name;

        Member(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }
    }

    static final class Team {
        private final List<Member> members = new ArrayList<>();

        void add(Member candidate) {
            Objects.requireNonNull(candidate);
            if (members.contains(candidate)) {
                throw new IllegalArgumentException("duplicate reference");
            }
            members.add(candidate);
        }

        List<Member> snapshot() {
            return List.copyOf(members);
        }

        String names() {
            List<String> result = new ArrayList<>();
            for (Member member : members) {
                result.add(member.name());
            }
            return result.toString();
        }
    }

    public static void main(String[] args) {
        Team team = new Team();
        Member mai = new Member("Mai");
        Member an = new Member("An");

        team.add(mai);
        team.add(an);

        System.out.println("members=" + team.names());
        System.out.println("size=" + team.snapshot().size());

        try {
            team.add(mai);
        } catch (IllegalArgumentException ex) {
            System.out.println("duplicate=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 OneToManyDemo.java
java OneToManyDemo
~~~

Stdout:

~~~text
members=[Mai, An]
size=2
duplicate=duplicate reference
~~~

Trong demo, Member không override `equals` nên `List.contains` dựa vào equality mặc định theo **object identity**. Hai Member instances khác nhau cùng tên vẫn có thể được thêm. Nếu “không trùng” thực sự nghĩa là cùng **business ID**, phải kiểm tra ID thay vì mặc định dùng reference identity.

`List.copyOf` cho một snapshot cấu trúc không sửa được qua các mutator List thông thường. Với Member chứa private final String trong demo, việc chia sẻ elements không tạo rủi ro mutable state đáng kể.

## 10. `List`, `Set` và `Map`

| Kiểu field | Có thứ tự? | Trùng lặp? | Nên dùng khi |
| --- | --- | --- | --- |
| `List<Member>` | Có thứ tự theo index | Có thể có | Cần vị trí/thứ tự hoặc cho phép lặp |
| `Set<Member>` | Tùy implementation | Không theo `equals/hashCode` | Cần tập không trùng |
| `LinkedHashSet<Member>` | Giữ insertion order | Không theo equality | Vừa không trùng vừa cần insertion order |
| `Map<MemberId, Member>` | Theo khóa, ordering tùy implementation | Keys không trùng | Lookup theo stable business ID |
| `Collection<Member>` | Contract tổng quát | Tùy concrete type | Giảm phụ thuộc vào implementation |

Không nên tự nghĩ “one-to-many thì bắt buộc ArrayList”. Một Department quản lý theo Employee ID có thể dùng `Map<String, Employee>`. Một Playlist có thể dùng List vì cần thứ tự và đôi khi bài hát lặp.

### Vì sao `Set` không tự giải quyết domain uniqueness?

`Set` dựa vào `equals/hashCode`. Nếu Employee chỉ dùng mặc định của Object, hai Employee instances khác nhau với cùng ID vẫn có thể cùng Set. Nếu Employee dùng mutable field trong hashCode rồi field thay đổi, `contains/remove` có thể thất bại khó hiểu. Hãy xác định identity business rõ ràng.

## 11. Một–nhiều hai chiều: Department ↔ Employee

Một Department giữ nhiều Employee references; mỗi Employee giữ tối đa một Department reference:

~~~text
Department A ----employees----> [Employee Mai, Employee An]
                                      |              |
                                      +--department--+
                                            |
                                            v
                                       Department A
~~~

Invariant mong muốn:

1. Nếu `employee.department == department`, danh sách `department.employees` chứa employee.
2. Nếu danh sách chứa employee, field `employee.department` trỏ về department.
3. Khi move employee sang department khác, gỡ khỏi danh sách cũ và thêm danh sách mới.
4. Khi remove, gỡ cả hai chiều.
5. Nếu duplicate không hợp lệ, không chứa same employee reference ở hai slots.

Java không tự duy trì các invariant đó. Nên có **một method điều phối** việc chuyển để caller không cập nhật mỗi bên tùy ý.

## 12. Ví dụ chạy: chuyển Employee giữa hai Departments

Tạo **`BidirectionalOneToManyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BidirectionalOneToManyDemo {
    static final class Employee {
        private final String name;
        private Department department;

        Employee(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }

        String departmentName() {
            return department == null ? "none" : department.name();
        }
    }

    static final class Department {
        private final String name;
        private final List<Employee> employees = new ArrayList<>();

        Department(String name) {
            this.name = Objects.requireNonNull(name);
        }

        String name() {
            return name;
        }

        void add(Employee employee) {
            Objects.requireNonNull(employee);
            if (employee.department == this) {
                return;
            }

            Department previous = employee.department;
            if (previous != null) {
                previous.employees.remove(employee);
            }

            employees.add(employee);
            employee.department = this;
        }

        void remove(Employee employee) {
            Objects.requireNonNull(employee);
            if (employee.department != this) {
                return;
            }
            employees.remove(employee);
            employee.department = null;
        }

        String names() {
            List<String> result = new ArrayList<>();
            for (Employee e : employees) {
                result.add(e.name());
            }
            return result.toString();
        }
    }

    public static void main(String[] args) {
        Department backend = new Department("Backend");
        Department frontend = new Department("Frontend");
        Employee mai = new Employee("Mai");
        Employee an = new Employee("An");

        backend.add(mai);
        frontend.add(an);

        System.out.println("before Backend=" + backend.names());
        System.out.println("before Frontend=" + frontend.names());

        frontend.add(mai);
        System.out.println("after Backend=" + backend.names());
        System.out.println("after Frontend=" + frontend.names());
        System.out.println("Mai=" + mai.departmentName());

        frontend.remove(an);
        System.out.println("An=" + an.departmentName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BidirectionalOneToManyDemo.java
java BidirectionalOneToManyDemo
~~~

Stdout:

~~~text
before Backend=[Mai]
before Frontend=[An]
after Backend=[]
after Frontend=[An, Mai]
Mai=Frontend
An=none
~~~

### Theo dõi sau `frontend.add(mai)`

- Ban đầu `mai.department` trỏ Backend; Backend.employees chứa Mai.
- Lệnh `previous.employees.remove(mai)` gỡ reference khỏi Backend list.
- `frontend.employees.add(mai)` thêm reference vào Frontend list.
- `mai.department = frontend` cập nhật field ngược.

Không có Employee mới được tạo khi chuyển. Object Mai vẫn cùng identity.

Code cố ý đặt Employee/Department thành các **nested classes trong cùng outer class**, nơi Java 17 cho phép các nestmates truy cập private fields theo quy tắc hiện hành. Khi tách thành hai top-level classes, phải thiết kế helper methods, quyền package hoặc một service quản lý relation — không nên mở toàn bộ fields thành public.

**Giới hạn:** Demo giả định thực thi tuần tự trong bộ nhớ. Nó chưa xử lý transaction, lỗi trong quá trình cập nhật, nhiều threads hoặc persistence. Trong thực tế cần kiểm tra tất cả preconditions **trước mutation**, và nếu nhiều bước có thể thất bại phải đảm bảo atomicity/rollback thích hợp.

## 13. Vì sao không công khai hai setters độc lập?

Một API dễ lỗi:

~~~java
employee.setDepartment(frontend);
frontend.getEmployees().add(employee);
backend.getEmployees().remove(employee);
~~~

Caller có thể quên bất kỳ dòng nào, thực hiện sai thứ tự hoặc gặp exception giữa chừng. Kết quả: field Employee.department và các Department lists **không nhất quán**.

Ưu tiên operation:

~~~java
frontend.add(employee);
~~~

hoặc:

~~~java
employee.transferTo(frontend);
~~~

với implementation thực sự chịu trách nhiệm cập nhật cả hai phía. Đối với domain nhiều aggregate hoặc có database, một `transferEmployee` service có transaction và kiểm tra quyền có thể là boundary hợp lý hơn.

“Owner” trong domain API nghĩa là **nơi chịu trách nhiệm invariant**, không tự đồng nghĩa “owning side” của JPA/Hibernate; ORM mapping còn có những quy tắc lưu khóa ngoại riêng.

## 14. Private fields và snapshots

Một field:

~~~java
private final List<Member> members = new ArrayList<>();
~~~

không ngăn mutation của List, nhưng giữ reference không bị gán lại. Nếu API:

~~~java
List<Member> members() {
    return members;
}
~~~

caller có thể `clear()` hoặc `add(null)` để phá validation của Team.

Một lựa chọn:

~~~java
List<Member> membersSnapshot() {
    return List.copyOf(members);
}
~~~

`List.copyOf` trả một List không sửa cấu trúc được qua List mutators, và không phản ánh các thay đổi cấu trúc sau đó của mutable List nguồn. Nhưng **không deep-copy Member objects**. Nếu Member mutable, các aliases khác vẫn có thể sửa Member được snapshot tham chiếu.

### Ví dụ runnable về shallow snapshot

Tạo **`ShallowSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowSnapshotDemo {
    static final class Task {
        private boolean done;

        void complete() {
            done = true;
        }

        boolean done() {
            return done;
        }
    }

    static final class Project {
        private final List<Task> tasks = new ArrayList<>();

        void add(Task task) {
            tasks.add(java.util.Objects.requireNonNull(task));
        }

        List<Task> tasksSnapshot() {
            return List.copyOf(tasks);
        }
    }

    public static void main(String[] args) {
        Project project = new Project();
        Task task = new Task();
        project.add(task);
        List<Task> snapshot = project.tasksSnapshot();

        System.out.println("before=" + snapshot.get(0).done());
        task.complete();
        System.out.println("after=" + snapshot.get(0).done());

        try {
            snapshot.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot cannot be cleared");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShallowSnapshotDemo.java
java ShallowSnapshotDemo
~~~

Stdout:

~~~text
before=false
after=true
snapshot cannot be cleared
~~~

**Kết luận:** Có thể đã khóa **cấu trúc relation list** đối với caller nhưng vẫn chia sẻ mutable **element state**. Nếu API hứa snapshot bất biến hoàn toàn, phải snapshot phần tử hoặc dùng immutable value objects.

## 15. Object identity và equality

Hai kiểu so sánh phổ biến:

- `a == b`: hai references có biểu thị **cùng object** hay không.
- `a.equals(b)`: theo contract của class, hai objects có **bằng nhau về giá trị/business identity** hay không.

~~~java
record MemberId(String id) {}

MemberId x = new MemberId("M1");
MemberId y = new MemberId("M1");
~~~

Trong Java 17, `x == y` là false vì hai record instances được tạo riêng; `x.equals(y)` là true vì components tương đương.

### Tiêu chí duplicate trong quan hệ

- **Cùng Java object:** check identity.
- **Cùng ID ổn định:** check `id` bằng equals hoặc Map key.
- **Cùng giá trị nội dung:** phù hợp với value object nhưng không luôn phù hợp với entity.

Không dùng tên hiển thị làm unique key nếu domain cho phép hai người trùng tên.

## 16. Một–nhiều dùng Map với business ID

Tạo **`OneToManyByIdDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OneToManyByIdDemo {
    record Member(String id, String name) {
        Member {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
        }
    }

    static final class Team {
        private final Map<String, Member> byId = new LinkedHashMap<>();

        void add(Member member) {
            if (member == null) {
                throw new IllegalArgumentException("member required");
            }
            if (byId.containsKey(member.id())) {
                throw new IllegalArgumentException("duplicate id");
            }
            byId.put(member.id(), member);
        }

        Member find(String id) {
            return byId.get(id);
        }

        List<Member> snapshot() {
            return List.copyOf(byId.values());
        }
    }

    public static void main(String[] args) {
        Team team = new Team();
        team.add(new Member("M1", "Mai"));
        team.add(new Member("M2", "Mai"));

        System.out.println("size=" + team.snapshot().size());
        System.out.println("M2=" + team.find("M2").name());

        try {
            team.add(new Member("M1", "Other"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("size again=" + team.snapshot().size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OneToManyByIdDemo.java
java OneToManyByIdDemo
~~~

Stdout:

~~~text
size=2
M2=Mai
rejected=duplicate id
size again=2
~~~

Có hai Members tên Mai nhưng khác ID nên đều hợp lệ. M1 lặp lại bị từ chối. `LinkedHashMap` duy trì insertion order trong demo. `Member` là record với String components, giúp giữ giá trị ID ổn định.

**Lưu ý về mutable hash keys:** Nếu dùng một entity mutable làm khóa của `HashMap`/phần tử `HashSet` và những fields tham gia `equals/hashCode` đổi sau khi thêm, `get/contains/remove` có thể không tìm được key theo mong đợi. Chọn key bất biến hoặc stable ID.

## 17. Association, aggregation và composition

Chúng có thể cùng dùng reference fields, nhưng khác ý nghĩa **ownership/lifecycle**:

**Association:** Quan hệ chung giữa objects; các objects có thể tồn tại độc lập. Ví dụ Teacher tham gia Course.

**Aggregation:** Một container gom các thành phần có vòng đời riêng. Ví dụ Department tập hợp Employees; Employee có thể chuyển Department.

**Composition:** Một chủ thể quản lý các phần với vòng đời gắn mạnh theo domain. Ví dụ Order có OrderLines riêng, không được share như entities giữa các orders.

Java không có keyword riêng để JVM tự phân biệt composition và aggregation. Cũng không tự “hủy child” ngay khi owner bị bỏ reference. Garbage collector làm việc theo reachability, không theo ký hiệu kim cương UML.

### So sánh với kế thừa

~~~java
class Car {
    private Engine engine; // HAS-A.
}

class ElectricCar extends Car {
    // IS-A: ElectricCar là một dạng Car.
}
~~~

`Car extends Engine` là mô hình sai nếu chỉ muốn xe **có** động cơ. Quan hệ has-a nên dùng reference field/composition; `extends` biểu diễn quan hệ is-a và quy tắc thừa kế.

## 18. Ví dụ composition một–nhiều: Order → OrderLines

Tạo **`OrderCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderCompositionDemo {
    record Line(String sku, int quantity, long unitPriceCents) {
        Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long subtotal() {
            return Math.multiplyExact(quantity, unitPriceCents);
        }
    }

    static final class Order {
        private final List<Line> lines = new ArrayList<>();

        void addLine(String sku, int quantity, long price) {
            Line line = new Line(sku, quantity, price);
            line.subtotal();
            lines.add(line);
        }

        List<Line> snapshot() {
            return List.copyOf(lines);
        }

        long total() {
            long result = 0;
            for (Line line : lines) {
                result = Math.addExact(result, line.subtotal());
            }
            return result;
        }
    }

    public static void main(String[] args) {
        Order order = new Order();
        order.addLine("P1", 2, 100);
        order.addLine("P2", 1, 50);

        System.out.println("lines=" + order.snapshot().size());
        System.out.println("total=" + order.total());

        try {
            order.snapshot().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot protected");
        }

        System.out.println("total again=" + order.total());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderCompositionDemo.java
java OrderCompositionDemo
~~~

Stdout:

~~~text
lines=2
total=250
snapshot protected
total again=250
~~~

`Order` tạo Line values thông qua một domain operation; caller không sửa trực tiếp List. `Line` là record chứa String/primitive fields; các line objects có state bất biến theo thiết kế trong demo.

**Không suy luận quá mức:** composition không ngăn hai Orders có hai Line objects **bằng nhau về giá trị**. Sở hữu domain lifecycle và value equality là các khái niệm khác nhau.

## 19. Thay reference khác với sửa object liên kết

Giả sử:

~~~java
Profile p = user.profile();
user.changeProfile(new Profile("An"));
~~~

nếu API cho phép, đây là **thay field reference**, khiến User trỏ object mới. Profile cũ có thể còn sống qua `p` hoặc references khác.

Ngược lại:

~~~java
user.profile().setName("An");
~~~

nếu Profile mutable, đây là **thay state của chính Profile object hiện tại**. Các aliases tới object đó có thể thấy name mới.

Một one-to-one relation có thể dùng **immutable Profile** để mỗi lần chỉnh dữ liệu tạo Profile mới, hoặc mutable Profile có API domain riêng. Không nên gọi hai hành vi đó cùng là “thay Profile” mà không xác định semantics.

### `final` field có bảo đảm bất biến không?

`private final Profile profile` chỉ ngăn reassign reference field trong code Java bình thường. Nếu Profile mutable, state Profile vẫn có thể thay đổi. Nếu two Users cùng giữ một Profile mutable, sửa từ một User có thể ảnh hưởng User kia.

## 20. Quan hệ và truyền tham trị

Java luôn **pass-by-value**. Với reference argument, method nhận **bản sao reference value**.

~~~java
static void replace(Team team) {
    team = new Team();
}
~~~

Việc gán lại parameter `team` không khiến biến Team ở caller trỏ object mới. Nhưng:

~~~java
static void add(Team team, Member member) {
    team.add(member);
}
~~~

có thể sửa collection bên trong Team object mà caller vẫn tham chiếu. Đây là mảnh minh họa, dùng types/methods phù hợp.

Điều quan trọng là phân biệt:

- Gán biến reference: đổi **mũi tên từ biến**.
- Gán field reference: đổi **mũi tên từ object field**.
- Thêm phần tử List: sửa **container object**.
- Sửa field của element: sửa **object đích mà List đang tham chiếu**.

## 21. Null và empty collection

Với relation tùy chọn `0..1`, field nullable có thể mang nghĩa “chưa liên kết”.

Với relation `0..*`, thường nên dùng **List rỗng** thay vì collection field null:

~~~java
private final List<Member> members = new ArrayList<>();
~~~

Caller không phải kiểm tra cả null và empty. Nếu domain yêu cầu `1..*`, constructor/factory hoặc validation của operations phải đảm bảo ít nhất một member tồn tại, kể cả sau remove.

### Không dùng Optional cho mọi collection

`Optional<List<Member>>` thường không cần nếu empty List có nghĩa hợp lý. Optional phù hợp hơn với **một quan hệ có thể vắng mặt** hoặc một query lookup có thể không thấy.

Không bao giờ coi thiếu dữ liệu bắt buộc là null hợp lệ chỉ vì dễ triển khai: hãy xác định invariant trước.

## 22. Gỡ liên kết không xóa object ngay

Nếu `department.remove(employee)`, code chỉ bỏ reference khỏi List và có thể đặt `employee.department = null`. Employee object vẫn có thể được biến local, service, registry hoặc collection khác tham chiếu.

Nếu không còn đường tham chiếu reachable, GC **có thể** thu hồi object khi thích hợp; không có cam kết thu hồi tức thì hay lệnh delete object theo cú pháp Java core.

Điều này cũng đúng với composition: “child bị xóa khỏi owner” là chính sách domain/persistence, không tự đồng nghĩa heap object biến mất ngay lập tức.

## 23. Quan hệ hai chiều, chu kỳ và `toString`

Một bidirectional Department/Employee graph có thể tạo cycle:

~~~text
Department ----> Employee
     ^              |
     +--------------+
~~~

GC hiện đại có thể xử lý unreachable cycles; bản thân cycle **không đủ chứng minh memory leak**. Nhưng nếu `Department.toString()` in Employees, còn `Employee.toString()` in Department, việc gọi lẫn nhau vô hạn có thể dẫn đến `StackOverflowError`.

Để log:

- In Employee ID hoặc Department name thay vì toàn object graph.
- Giới hạn độ sâu nếu cần traverse.
- Dùng visited set theo identity nếu duyệt graph có cycle.
- Với JSON serialization, thiết kế DTO hoặc cấu hình xử lý reference cycles theo thư viện.

### Chương trình chạy: in không đệ quy

Tạo **`SafeCycleDemo.java`**:

~~~java
public class SafeCycleDemo {
    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void link(Node node) {
            next = node;
        }

        String describe() {
            return name + " -> " +
                    (next == null ? "none" : next.name);
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.link(b);
        b.link(a);

        System.out.println(a.describe());
        System.out.println(b.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeCycleDemo.java
java SafeCycleDemo
~~~

Stdout:

~~~text
A -> B
B -> A
~~~

Hai Node tham chiếu nhau nhưng `describe()` chỉ đọc tên của node kế tiếp, không gọi `next.describe()`, nên không đệ quy vô hạn.

## 24. Static collections và vòng đời reference

Một global registry:

~~~java
static final List<Listener> LISTENERS = new ArrayList<>();
~~~

có thể giữ references đến những objects đáng lẽ đã hết vòng đời. Nếu Listener giữ User/Service/UI components, cả graph có thể còn reachable vì static List.

Đối với quan hệ nhiều object có lifecycle, cần:

- `unregister/remove`.
- Tránh giữ request/session data trong static collection toàn cục.
- Giới hạn kích thước/eviction khi cần.
- Có owner và cleanup rõ.
- Thiết kế tests dùng instance registry thay vì trạng thái toàn cục khi có thể.

**Cycle không tự là memory leak**; reference path còn reachable từ GC roots mới là yếu tố quyết định.

## 25. Concurrency: quan hệ nhất quán trong nhiều threads

`ArrayList` không tự thread-safe. Code kiểu:

~~~java
if (!members.contains(member)) {
    members.add(member);
}
~~~

là **check-then-act**. Hai threads có thể cùng nhìn thấy chưa có rồi đều thêm, phá invariant “không trùng”.

Với bidirectional relationship, một thread chuyển Employee sang Department A trong khi thread khác chuyển sang B có thể tạo trạng thái lệch nếu không phối hợp.

Các cách xử lý tùy hệ thống:

- Đặt lock/synchronization quanh **toàn bộ thao tác kiểm tra và cập nhật liên kết**, không chỉ một lệnh `add`.
- Chọn collection concurrent phù hợp với semantics và atomic operations cụ thể.
- Dùng single-owner thread hoặc actor/message passing khi thích hợp.
- Với dữ liệu persistent, dùng transaction, unique constraints/foreign keys và concurrency control.
- Xác định thứ tự lock để giảm nguy cơ deadlock nếu cập nhật nhiều owners.

`final` reference không tự làm mutable collection thread-safe; `Collections.synchronizedList` cũng không tự bảo đảm một operation đa bước liên quan Employee.department và nhiều Lists là atomic.

## 26. Java models và database/ORM

Khi học Java core, các reference fields chỉ mô tả **in-memory object graph**. Một hệ thống có database bổ sung:

- Primary key, foreign key và unique constraints.
- Transaction khi cập nhật quan hệ.
- Lazy/eager loading và object identity map theo ORM.
- Cascade operations/orphan removal khi domain yêu cầu.
- Mapping “owning side” theo framework.

Không suy luận rằng JPA `@OneToMany` là một Java keyword hoặc một List tự ghi database ngay khi `add`. Framework áp dụng quy tắc mapping/persistence riêng.

Một bidirectional Java graph đúng **chưa chứng minh database state đúng**, và ngược lại database constraint không tự sửa những field references đã lệch trong heap nếu code không refresh/synchronize chúng. Cần kiểm tra cả hai tầng khi có ORM.

## 27. Test quan hệ hai chiều

Với `Department.add(employee)`, đừng chỉ assert list count. Hãy test:

1. Thêm Employee mới: Department chứa đúng reference; Employee.department trỏ ngược.
2. Thêm lại cùng Employee: chính sách idempotent hoặc ném lỗi rõ.
3. Chuyển từ A sang B: A không chứa Employee; B chứa; Employee.department == B.
4. Remove khỏi B: cả hai hướng được gỡ.
5. Null input: bị từ chối nếu không hợp lệ.
6. Two Employees có cùng name/ID: xử lý theo uniqueness contract.
7. Nếu operation thất bại, không còn state nửa chừng.
8. Nếu hỗ trợ parallel execution, test invariant dưới concurrency.

Một assertion chỉ kiểm tra `employee.departmentName()` không đủ để phát hiện employee còn nằm trong old Department list.

### Tự động hóa test

Trong ứng dụng thực tế có thể dùng JUnit để kiểm tra `assertSame`, `assertTrue`, `assertFalse`, `assertThrows`. Nhưng mẫu Java 17+ trong bài dùng `main` và stdout để tự kiểm chứng mà không cần thư viện bên ngoài.

## 28. Các lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách sửa |
| --- | --- | --- |
| Field reference tự tạo object | NullPointerException | Khởi tạo explicit |
| Một reference field tự bảo đảm one-to-one độc quyền | Nhiều owners dùng chung target | Thêm constraint/backreference/owner |
| Hai references được cập nhật tự động | Inverse relation lệch | Một operation điều phối cả hai |
| `List<Member>` tạo Member objects | Danh sách rỗng | Tạo/lấy members rồi thêm |
| List có 2 entries tức 2 distinct objects | Duplicate aliases | Xét object IDs và uniqueness |
| `List.copyOf` deep-copy Member | Mutable Member còn shared | Immutable element/copy theo hợp đồng |
| Private final List nghĩa là List bất biến | Caller/method vẫn mutate List | Che đường mutate, snapshot |
| Mọi một–nhiều bắt buộc hai chiều | Coupling tăng không cần | Chọn hướng theo use case |
| Dùng mutable business field làm hash key | contains/remove sai kỳ vọng | Stable key |
| Dùng `extends` để biểu thị “has-a” | Sai ngữ nghĩa subtype | Reference field/composition |
| Bỏ reference là object bị xóa ngay | Sai về GC | Hiểu reachability |
| Cycle luôn leak memory | Sai về GC | Kiểm tra GC roots |
| In toàn graph trong toString | Infinite recursion | In ID/name, xử lý visited |
| Check-then-add với ArrayList là atomic | Race, duplicates | Lock/atomic operations |
| ORM annotation tự sửa Java field ngược | Inconsistent graph | Quản lý in-memory association rõ |
| Không test remove/move/fail | Invariant chỉ đúng happy path | Kiểm thử mọi transition |

## 29. Quy trình thiết kế quan hệ theo từng bước

**Bước 1:** Liệt kê hai kiểu object và use cases điều hướng.

**Bước 2:** Viết **cardinality từ cả hai phía**: `0..1`, `1`, `0..*`, `1..*` hoặc giới hạn N.

**Bước 3:** Chọn **một chiều/hai chiều**. Nếu chỉ truy cập từ A tới B, không thêm backreference không cần thiết.

**Bước 4:** Chọn representation: một field tới object hoặc field tới List/Set/Map.

**Bước 5:** Xác định **identity** và duplicate rule: same instance, stable ID hay value equality.

**Bước 6:** Chọn **owner** thực hiện mutation: constructor/factory, method của A/B hoặc domain service.

**Bước 7:** Bảo vệ invariants qua non-null validation, private fields, operation có nghĩa và snapshots.

**Bước 8:** Viết đầy đủ operations attach/detach/replace/move, kể cả xử lý previous link.

**Bước 9:** Quy định lifecycle/ownership: object con tồn tại độc lập không, có shared aliases không, cleanup ra sao.

**Bước 10:** Thử failure cases, concurrency và persistence constraints nếu hệ thống yêu cầu.

## 30. Bài tập 1 — Một field có đủ bảo đảm one-to-one?

~~~java
Profile shared = new Profile();
User a = new User();
User b = new User();
a.profile = shared;
b.profile = shared;
~~~

Các khai báo này là đoạn minh họa với public/package fields và constructors phù hợp.

**Đáp án:** Có hai User objects và **một Profile object**. Cả hai Users cùng tham chiếu Profile. Không có uniqueness constraint. Muốn Profile thuộc tối đa một User, cần bảo vệ qua relation operation và backreference/registry hoặc constraint ở persistence layer.

## 31. Bài tập 2 — Duplicate reference trong List

~~~java
Member mai = new Member("Mai");
List<Member> members = new ArrayList<>();
members.add(mai);
members.add(mai);
System.out.println(members.size());
System.out.println(members.get(0) == members.get(1));
~~~

**Đáp án:**

~~~text
2
true
~~~

Hai list slots trỏ cùng Member object. Nếu domain cấm duplicate identity, kiểm tra trước add hoặc dùng representation phù hợp.

## 32. Bài tập 3 — Chuyển ownership

Cho trạng thái:

~~~text
A.employees = [Mai, An]
B.employees = [Binh]
Mai.department -> A
An.department -> A
Binh.department -> B
~~~

Sau `B.add(Mai)` với hợp đồng mỗi Employee thuộc tối đa một Department:

~~~text
A.employees = [An]
B.employees = [Binh, Mai]
Mai.department -> B
An.department -> A
Binh.department -> B
~~~

Nếu A vẫn chứa Mai, invariant đã sai. Hãy viết test kiểm tra **cả hai collections lẫn backreference**.

## 33. Bài tập 4 — Bảo vệ private collection

~~~java
class Team {
    private final List<Member> members = new ArrayList<>();
    List<Member> members() {
        return members;
    }
}
~~~

**Câu hỏi:** Caller có thể `team.members().clear()` không? Điều đó có bypass validation không?

**Đáp án:** Có. Getter trả nguyên mutable List. Thay bằng query/snapshot và methods `addMember`/`removeMember`. Nhưng List snapshot không tự deep-copy Member objects nếu Member mutable.

## 34. Bài tập 5 — Chọn kiểu collection

Chọn representation cho:

- Playlist cần thứ tự và cho phép bài hát xuất hiện nhiều lần.
- Department truy cập Employee theo stable ID.
- Tập tag không trùng.
- OrderLines có vị trí trình bày.
- Một Customer có tối đa một loyalty card.

**Đáp án gợi ý:** Playlist: List; Department: Map<ID, Employee>; Tags: Set; OrderLines: List; Customer → Card: single reference field. Luôn bổ sung validation để bảo vệ cardinality và integrity.

## 35. Bài tập 6 — Composition hay aggregation?

Một Order sở hữu các Line values của nó. Một Team chứa Employees có thể chuyển sang Team khác.

**Đáp án:** Order–Line phù hợp composition về vòng đời; Team–Employee thường phù hợp association/aggregation. Cả hai dùng Java references/collections; khác nhau ở **hợp đồng ownership**, không phải modifier hay hình thức field.

## 36. Bài tập 7 — Cycle không phải GC leak tự động

Một Department giữ Employee; Employee giữ Department.

**Câu hỏi:** Cycle có ngăn garbage collector thu hồi cả hai mãi mãi không?

**Đáp án:** Không. Nếu không có reference path từ GC roots đến cycle, các objects có thể được thu hồi. Nhưng static registry giữ Department/Employee reference có thể khiến chúng tiếp tục reachable và gây memory retention. Không cần phá mọi cycle chỉ để GC làm việc.

## 37. Checklist cuối bài

- [ ] Tôi biết field reference lưu reference value hoặc null, không tự tạo object.
- [ ] Tôi hiểu một field đơn không tự tạo uniqueness toàn domain.
- [ ] Tôi đọc được bội số của quan hệ ở hai hướng.
- [ ] Tôi biết constructor non-null cho quan hệ bắt buộc.
- [ ] Tôi có thể dùng Optional ở API cho quan hệ tùy chọn.
- [ ] Tôi biết gán một field không tự cập nhật backreference.
- [ ] Tôi thiết kế được một–một hai chiều có kiểm tra uniqueness.
- [ ] Tôi tạo được một–nhiều bằng private List/Set/Map.
- [ ] Tôi phân biệt collection object với element objects.
- [ ] Tôi biết một List có thể chứa hai references tới cùng object.
- [ ] Tôi phân biệt identity, equals và stable business ID.
- [ ] Tôi biết rủi ro Set/Map nếu hash keys mutable.
- [ ] Tôi chuyển Employee giữa Department mà không phá invariant.
- [ ] Tôi hiểu tại sao raw mutable List getter phá encapsulation.
- [ ] Tôi hiểu List.copyOf không deep-copy các elements mutable.
- [ ] Tôi phân biệt association, aggregation, composition và inheritance.
- [ ] Tôi biết đổi reference khác với sửa state object.
- [ ] Tôi biết bỏ reference không xóa object ngay.
- [ ] Tôi tránh toString/serialization recursion qua cycle.
- [ ] Tôi biết static collection có thể giữ object graph reachable lâu.
- [ ] Tôi không nghĩ ArrayList và check-then-act tự thread-safe.
- [ ] Tôi hiểu quan hệ Java in-memory khác constraints/transactions trong DB.
- [ ] Tôi viết test cho attach, detach, transfer, duplicate và fail paths.
- [ ] Tôi tự biên dịch, chạy và giải thích các ví dụ Java 17+ trong bài.

**Kết luận:** Quan hệ **một–một** được biểu diễn cơ bản bằng **một trường tham chiếu**, quan hệ **một–nhiều** bằng **một trường tham chiếu tới collection**. Nhưng những cấu trúc đó **chỉ lưu các reference values**. Tính duy nhất, ownership, số lượng tối thiểu/tối đa, vòng đời child và sự nhất quán hai chiều là **invariants do thiết kế class và API phải bảo vệ**. Hãy chọn một chiều hay hai chiều theo use case, dùng List/Set/Map theo semantics, giữ fields private, cung cấp thao tác có nghĩa và kiểm thử kỹ các đường thêm, xóa, chuyển và thất bại.
