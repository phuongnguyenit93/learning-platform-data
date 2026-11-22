# Nhiều tham chiếu cùng trỏ đến một đối tượng trong Java

Trong lập trình hướng đối tượng (OOP), một **đối tượng (object)** có thể được truy cập thông qua **nhiều biến tham chiếu (reference variables)**. Điều này thường xảy ra khi gán một biến đối tượng cho biến khác, truyền đối tượng vào phương thức, lấy đối tượng từ collection hoặc trả về đối tượng qua getter.

Điểm quan trọng: **sao chép tham chiếu không tạo ra đối tượng mới**. Khi hai biến cùng tham chiếu đến một đối tượng có thể thay đổi (mutable), việc cập nhật trạng thái đối tượng qua một biến sẽ được nhìn thấy qua biến còn lại.

## 1. Tham chiếu khác với đối tượng như thế nào?

Với khai báo:

~~~java
Student student = new Student("An");
~~~

- `new Student("An")` tạo một đối tượng `Student` mới.
- `student` là biến tham chiếu dùng để truy cập đối tượng đó.
- Biến tham chiếu không chứa bản sao của toàn bộ `Student`; nó mang giá trị tham chiếu đến đối tượng.
- Nếu khai báo thêm `Student another = student;`, Java sao chép **giá trị tham chiếu**, không tạo `Student` thứ hai.

Ví dụ:

~~~java
Student a = new Student("An");
Student b = a;
~~~

~~~mermaid
flowchart LR
    A["Tham chiếu a"] --> O["Một đối tượng Student\nname = An"]
    B["Tham chiếu b"] --> O
~~~

Sơ đồ là **mô hình khái niệm** về quan hệ tham chiếu, không mô tả vị trí bộ nhớ vật lý hoặc địa chỉ thật. Cả `a` và `b` đều truy cập **cùng một instance**.

So sánh với kiểu nguyên thủy:

~~~java
int x = 10;
int y = x; // Sao chép giá trị số nguyên
y = 20;

System.out.println(x); // 10
System.out.println(y); // 20
~~~

Trong ví dụ `int`, thay đổi `y` không ảnh hưởng `x` vì chúng là hai biến chứa giá trị riêng. Với biến tham chiếu, hai biến có thể cùng dẫn đến một đối tượng nên kết quả phụ thuộc vào việc ta **thay đổi đối tượng** hay **gán lại biến tham chiếu**.

## 2. Ví dụ chạy được: hai tham chiếu cùng quan sát một thay đổi

`Main.java`:

~~~java
import java.util.Objects;

public class Main {
    static class Student {
        private String name;

        Student(String name) {
            setName(name);
        }

        String getName() {
            return name;
        }

        void setName(String name) {
            String checked = Objects.requireNonNull(name, "name").trim();
            if (checked.isEmpty()) {
                throw new IllegalArgumentException("Tên không được rỗng");
            }
            this.name = checked;
        }
    }

    public static void main(String[] args) {
        Student first = new Student("An");
        Student second = first; // Không gọi new

        System.out.println(first == second);  // true
        System.out.println(first.getName());   // An

        second.setName("Bình"); // Thay đổi đối tượng dùng chung

        System.out.println(first.getName());   // Bình
        System.out.println(second.getName());  // Bình
    }
}
~~~

Giải thích từng lệnh:

1. `new Student("An")` tạo **một** đối tượng, `first` trỏ đến nó.
2. `second = first` chép giá trị tham chiếu; vẫn chỉ có **một** đối tượng.
3. `second.setName("Bình")` thay đổi thuộc tính `name` trên đối tượng ấy.
4. Vì `first` trỏ đến cùng đối tượng, `first.getName()` cũng trả về `Bình`.

Điều này được gọi là **aliasing**: nhiều tham chiếu đóng vai trò các “tên” khác nhau để truy cập cùng một đối tượng.

## 3. Phân biệt thay đổi trạng thái và gán lại tham chiếu

Hai thao tác dưới đây tạo ra kết quả hoàn toàn khác nhau.

### Trường hợp A: thay đổi chính đối tượng

~~~java
Student a = new Student("An");
Student b = a;

b.setName("Chi");

System.out.println(a.getName()); // Chi
System.out.println(a == b);      // true
~~~

`b.setName(...)` tác động lên **đối tượng được trỏ tới**. Cả `a` và `b` vẫn cùng trỏ đến đối tượng ban đầu.

### Trường hợp B: gán lại biến tham chiếu

~~~java
Student a = new Student("An");
Student b = a;

b = new Student("Dung"); // Tạo đối tượng mới, thay tham chiếu ở b

System.out.println(a.getName()); // An
System.out.println(b.getName()); // Dung
System.out.println(a == b);      // false
~~~

~~~mermaid
flowchart LR
    A["a"] --> O1["Student #1\nname = An"]
    B["b"] --> O2["Student #2\nname = Dung"]
~~~

Phép gán `b = new Student(...)` chỉ thay **giá trị của biến b**. Nó không sửa `a` và cũng không xóa hay tự thay thế đối tượng mà `a` đang trỏ tới.

Một phép gán nữa có thể khiến hai biến lại trỏ chung:

~~~java
b = a;
System.out.println(a == b); // true
~~~

Bảng phân biệt:

| Câu lệnh | Có tạo đối tượng mới? | `a` có bị thay tham chiếu? | Có thể thấy thay đổi qua `a`? |
| --- | --- | --- | --- |
| `Student b = a;` | Không | Không | Hai biến đang chia sẻ cùng instance |
| `b.setName("Chi");` | Không | Không | Có, `a.getName()` cũng thấy “Chi” |
| `b = new Student("Dung");` | Có | Không | Không; `a` vẫn chỉ đến instance cũ |
| `b = null;` | Không | Không | Không; chỉ `b` thôi không còn trỏ đến instance |
| `a = b;` | Không | Có | `a` trỏ đến instance mà `b` đang trỏ tới |

**Quy tắc nhớ:** gọi phương thức làm thay đổi trạng thái qua một tham chiếu sẽ ảnh hưởng đến đối tượng chung; gán lại một biến tham chiếu chỉ tác động lên chính biến ấy.

## 4. Làm sao chứng minh có đúng cùng một instance?

Trong Java, `a == b` trên tham chiếu xác nhận hai biến cùng trỏ đến **một đối tượng** (hoặc đều là `null`). Nếu tạo hai instance chứa cùng dữ liệu, chúng vẫn khác identity:

~~~java
record Point(int x, int y) {}
Point a = new Point(3, 5);
Point b = new Point(3, 5);
Point alias = a;

System.out.println(a == alias); // true
System.out.println(a == b);     // false
System.out.println(a.equals(b)); // true: Point so sánh giá trị
~~~

`equals()` trả lời một câu hỏi **khác**: lớp có coi hai giá trị là tương đương không? Nó không phải phép thử alias. Hợp đồng `equals/hashCode`, `String` và các collection được đào sâu ở bài tiếp theo.

## 5. Aliasing có thể xảy ra bên trong cùng một lời gọi phương thức

Java truyền đối số **theo giá trị**. Khi đối số là object, tham số nhận bản sao giá trị tham chiếu, nên hai tham số còn có thể trỏ tới **cùng một object**:

~~~java
static void incrementBoth(Box x, Box y) {
    x.value++;
    y.value++;
}

Box box = new Box(0);
incrementBoth(box, box);
System.out.println(box.value); // 2
~~~

Đoạn này giả sử lớp `Box` có field `int value` và constructor nhận giá trị đầu. Dù phương thức khai báo **hai biến tham số**, caller truyền cùng một object hai lần. Khi phương thức làm thay đổi cả `x.value` và `y.value`, hai lệnh đều tác động lên `box`. Đây là hệ quả quan trọng khi thiết kế API nhận nhiều đối tượng và giả định sai rằng chúng độc lập.

Gán `x = new Box(...)` bên trong phương thức lại chỉ đổi tham số `x`; biến tham chiếu phía caller không bị gán lại. Bài *Tham chiếu, giá trị và cách truyền đối tượng* có ví dụ đầy đủ về pass-by-value và hoán đổi tham số.

## 6. Nhiều tham chiếu xuất hiện tự nhiên trong chương trình

### Qua collection

~~~java
import java.util.ArrayList;
import java.util.List;

Student student = new Student("An");
List<Student> students = new ArrayList<>();

students.add(student);          // List lưu tham chiếu đến student
Student fromList = students.get(0);

System.out.println(student == fromList); // true

fromList.setName("Hoa");
System.out.println(student.getName());   // Hoa
~~~

`List<Student>` giữ các phần tử dưới dạng tham chiếu đến đối tượng `Student`, không tự tạo bản sao sâu của từng đối tượng khi `add` hoặc `get`.

### Qua quan hệ giữa các đối tượng

~~~java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Employee {
    Address address;

    Employee(Address address) {
        this.address = address;
    }
}

Address shared = new Address("Hà Nội");

Employee e1 = new Employee(shared);
Employee e2 = new Employee(shared);

e1.address.city = "Đà Nẵng";
System.out.println(e2.address.city); // Đà Nẵng
~~~

Ở ví dụ này, hai `Employee` là **hai đối tượng khác nhau**, nhưng trường `address` của chúng lại trỏ đến **cùng một đối tượng Address**. Đây là chia sẻ tham chiếu theo quan hệ đối tượng; không phải mọi thuộc tính của `e1` và `e2` đều chia sẻ.

Sơ đồ:

~~~mermaid
flowchart LR
    E1["Employee e1"] --> A["Address\ncity = Đà Nẵng"]
    E2["Employee e2"] --> A
~~~

Trong hệ thống thực tế, chia sẻ `Address` có thể đúng nếu hai nhân viên cùng tham chiếu một bản ghi địa chỉ chung; nhưng có thể là **bug** nếu mỗi người cần một địa chỉ độc lập.

## 7. Cần phân biệt alias với bản sao chứa các alias bên trong

~~~java
List<Student> original = new ArrayList<>();
original.add(new Student("An"));

List<Student> copied = new ArrayList<>(original);
System.out.println(original == copied);             // false
System.out.println(original.get(0) == copied.get(0)); // true
~~~

`copied` là **một đối tượng List khác**, nhưng phần tử `Student` vẫn là đối tượng được chia sẻ; gọi `copied.get(0).setName("Lan")` có thể làm `original.get(0).getName()` trả `"Lan"`. Ngược lại, thêm phần tử vào `copied` không tự thay đổi cấu trúc `original`.

Đây là lý do **“hai container khác nhau” không bảo đảm “mọi đối tượng bên trong khác nhau”**. Cách tạo bản sao nông, bản sao sâu, bảo toàn shared references và xử lý đồ thị vòng nằm ở bài *Sao chép nông và sao chép sâu*.

## 8. Chia sẻ đối tượng bất biến thì sao?

Một đối tượng immutable như `String` hoặc `LocalDate` vẫn có thể có nhiều alias. Điểm khác là nội dung của chính instance ấy không bị sửa qua alias. Ví dụ `String b = a; b = b.toUpperCase();` gán `b` sang chuỗi kết quả, không thay chuỗi mà `a` đang tham chiếu.

`final Student owner = new Student("An");` cũng không ngăn `Student alias = owner; alias.setName("Bình");`: `final` chỉ ngăn **gán lại biến `owner`**. Khi cần tránh tác dụng phụ do nhiều alias, phải xét khả năng thay đổi trạng thái và cách công khai tham chiếu, như trình bày ở bài *Mutable/Immutable*.

## 9. Khi một alias không còn giữ đối tượng

~~~java
Student first = new Student("An");
Student second = first;
first = null;

System.out.println(second.getName()); // An
~~~

Đặt `first = null` chỉ bỏ **một đường tham chiếu**. Đối tượng vẫn có thể truy cập qua `second`. Khi không còn đường tham chiếu mạnh có thể truy cập từ GC roots, object *có thể* đủ điều kiện thu gom rác; điều này không bảo đảm được thu gom ngay. Bài *Giá trị rỗng và đối tượng chưa tồn tại* phân biệt chi tiết `null`, biến chưa khởi tạo và sự tồn tại của thực thể.

## 10. Những lỗi thực tế và cách phòng tránh

**Lỗi 1 — Vô tình thay đổi dữ liệu gốc khi chỉ muốn thử nghiệm:**

~~~java
Student draft = originalStudent;
draft.setName("Tên thử"); // originalStudent cũng bị thay đổi
~~~

Nếu muốn một đối tượng độc lập, hãy tạo bản sao phù hợp (constructor sao chép, factory hoặc mapping có chủ đích), thay vì chỉ gán một biến tham chiếu.

**Lỗi 2 — Làm lộ mutable field qua getter:**

~~~java
class Team {
    private final List<Student> members = new ArrayList<>();

    List<Student> getMembers() {
        return members; // Caller có thể clear(), add(), remove() tự do
    }
}
~~~

Có thể trả về `List.copyOf(members)` nếu muốn bảo vệ cấu trúc danh sách khỏi việc sửa từ bên ngoài. Tuy nhiên, vì các phần tử `Student` vẫn mutable, người gọi **vẫn có thể** sửa tên của từng `Student` qua tham chiếu được trả về. Muốn read-only hoàn toàn, cần trả về các DTO/value object bất biến hoặc bản sao bảo vệ mọi trạng thái cần thiết.

**Lỗi 3 — Nhầm chia sẻ tham chiếu với lỗi đồng thời:**

Khi nhiều **luồng** cùng giữ tham chiếu đến một đối tượng mutable, có thể phát sinh data race, lost update hoặc trạng thái không nhất quán. Việc nhiều alias cùng tồn tại **không tự động tạo ra race condition**; vấn đề xuất hiện khi thao tác đồng thời không được phối hợp.

~~~java
class Counter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int getValue() {
        return value;
    }
}
~~~

`synchronized` ở đây bảo vệ truy cập vào trạng thái `Counter` khi các luồng sử dụng cùng instance và các đường truy cập đều tuân thủ cùng cơ chế đồng bộ. Trong các hệ thống đa tiến trình hoặc nhiều service, cần cơ chế phối hợp phù hợp ở tầng dữ liệu/phân tán.

**Lỗi 4 — Đổi tham chiếu nhưng tưởng đã thay dữ liệu trong collection:**

~~~java
Student s = new Student("An");
List<Student> group = new ArrayList<>();
group.add(s);

s = new Student("Bình");

System.out.println(group.get(0).getName()); // An
System.out.println(group.get(0) == s);      // false
~~~

`group` vẫn chứa tham chiếu đến `Student("An")` ban đầu. Nếu muốn thay phần tử trong danh sách, cần thao tác trực tiếp trên danh sách, ví dụ `group.set(0, s)`.

## 11. Bộ câu hỏi tự kiểm tra

**Câu 1:** Nếu `Student b = a;`, trong bộ nhớ có bao nhiêu đối tượng `Student` mới được tạo bởi riêng câu lệnh này?

**Đáp án:** Không có. Đây là phép sao chép giá trị tham chiếu, không chứa `new`.

**Câu 2:** `a == b` là `true`. Nếu gọi `b.setName("Minh")`, kết quả `a.getName()` thay đổi không?

**Đáp án:** Có, nếu setter thay đổi thuộc tính `name` của đối tượng chung và lệnh thành công. Hai biến trỏ cùng instance.

**Câu 3:** Sau `b = new Student("Khác")`, liệu `a` tự trỏ đến đối tượng mới không?

**Đáp án:** Không. Chỉ `b` được gán lại; `a` vẫn giữ tham chiếu cũ.

**Câu 4:** `new ArrayList<>(oldList)` có tách biệt hoàn toàn mọi `Student` bên trong không?

**Đáp án:** Không. Nó tạo một List khác, song giữ cùng tham chiếu phần tử. Cần sao chép từng đối tượng mutable nếu cần trạng thái độc lập.

**Câu 5:** Java có truyền đối tượng theo tham chiếu (pass-by-reference) không?

**Đáp án:** Không. Java truyền **bản sao giá trị tham chiếu** theo cơ chế pass-by-value. Phương thức có thể sửa đối tượng chung nhưng không thể gán lại biến tham chiếu của người gọi chỉ bằng cách gán tham số.

**Câu 6:** Hai đối tượng khác instance nhưng có dữ liệu giống nhau có `== true` không?

**Đáp án:** Không, nếu thật sự là hai instance khác nhau. `equals()` có thể `true` nếu kiểu dữ liệu có định nghĩa bình đẳng theo nội dung.

Khi đọc hoặc viết code Java, hãy tự hỏi: **“Có bao nhiêu đối tượng đang tồn tại, biến nào đang giữ tham chiếu đến đối tượng nào, và câu lệnh sắp chạy đang sửa trạng thái đối tượng hay chỉ gán lại tham chiếu?”** Ba câu hỏi đó giúp giải thích phần lớn hiện tượng aliasing và tránh việc cập nhật dữ liệu ngoài ý muốn.