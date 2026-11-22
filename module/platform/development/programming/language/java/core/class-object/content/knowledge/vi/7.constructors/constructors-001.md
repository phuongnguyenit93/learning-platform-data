# Vai trò của hàm khởi tạo trong việc tạo trạng thái hợp lệ trong Java

**Constructor (hàm khởi tạo)** là cơ chế giúp một đối tượng Java được thiết lập trạng thái ban đầu khi được tạo. Một constructor tốt không chỉ gán tham số cho các field, mà còn **kiểm tra điều kiện đầu vào, xây dựng mối quan hệ nhất quán giữa các field và bảo đảm những bất biến (*invariants*) cần thiết** trước khi đối tượng được cung cấp cho code sử dụng.

Ví dụ: một tài khoản chỉ hợp lệ nếu mã không rỗng và số dư ban đầu không âm. Một khoảng thời gian chỉ hợp lệ nếu thời điểm bắt đầu không nằm sau thời điểm kết thúc. Constructor là nơi phù hợp để loại bỏ trạng thái sai **ngay tại điểm tạo đối tượng**, thay vì để các method phía sau liên tục đoán xem field đã được thiết lập đủ hay chưa.

Bài học áp dụng cho **Java 17+**, tập trung vào vai trò của constructor trong thiết kế class, vòng đời khởi tạo, bảo vệ bất biến, validation, `final`, defensive copying, constructor chaining và các bẫy làm lộ đối tượng chưa được khởi tạo hoàn chỉnh.

## 1. Constructor là gì và “trạng thái hợp lệ” nghĩa là gì?

Xét một class đơn giản:

~~~java
class Student {
    private final String studentId;
    private final int age;

    Student(String studentId, int age) {
        this.studentId = studentId;
        this.age = age;
    }
}
~~~

Đây là **đoạn khai báo**, không có method `main` để chạy độc lập. `Student(...)` là constructor: tên giống tên class và **không có khai báo kiểu trả về**, kể cả `void`.

Khi viết:

~~~java
Student student = new Student("SV-01", 20);
~~~

Java tạo một object `Student`, thực hiện quá trình khởi tạo tương ứng và gán **tham chiếu đến object** cho biến `student`. Constructor **không phải** là một method trả về object bằng câu lệnh `return student`; biểu thức `new Student(...)` mới có giá trị là tham chiếu tới object đã tạo.

Tuy nhiên, constructor đầu tiên ở trên **chưa thật sự bảo vệ trạng thái**: nó chấp nhận `studentId == null`, mã chỉ toàn khoảng trắng và tuổi âm. Object vẫn được tạo bằng lệnh `new`, nhưng có thể không hợp lệ theo nghiệp vụ.

Một **class invariant** là điều kiện phải đúng tại những thời điểm mà đối tượng được coi là ở trạng thái có thể sử dụng theo hợp đồng. Ví dụ:

- `studentId != null` và `!studentId.isBlank()`.
- `age >= 0` và `age <= 150` nếu đây là miền tuổi được ứng dụng quy định.
- `start <= end` nếu object biểu diễn một khoảng thời gian.
- `balance >= 0` nếu mô hình tài khoản không cho phép số dư âm.
- Danh sách các mục đã đăng ký không chứa `null` và không thể bị caller âm thầm sửa qua tham chiếu dùng chung.

**Constructor chịu trách nhiệm thiết lập invariant ban đầu**; những command/method thay đổi trạng thái về sau tiếp tục chịu trách nhiệm **duy trì** invariant ấy. Không có điều gì trong Java tự động biến một điều kiện nghiệp vụ thành đúng: phải viết code xác thực.

## 2. Các giai đoạn khởi tạo: đừng nhầm giá trị mặc định với trạng thái hợp lệ

Đối với object bình thường được tạo bằng `new`, các instance field bắt đầu có **giá trị mặc định theo kiểu** trước khi các field initializer, instance initializer và constructor body liên quan thực hiện theo thứ tự được Java quy định.

| Kiểu field | Giá trị mặc định |
| --- | --- |
| `byte`, `short`, `int`, `long` | Số `0` phù hợp kiểu |
| `float`, `double` | `0.0` phù hợp kiểu |
| `char` | `'\u0000'`, UTF-16 code unit U+0000 |
| `boolean` | `false` |
| Kiểu tham chiếu, ví dụ `String`, mảng, class | `null` |

Ví dụ:

~~~java
class UserProfile {
    private String username; // mặc định null
    private int age;         // mặc định 0
}
~~~

Khi gọi `new UserProfile()` nếu class không khai báo constructor, Java cung cấp **default constructor** không tham số phù hợp các quy tắc của ngôn ngữ. Nhưng việc một object có field `username == null` có thể khiến nó **không hợp lệ để sử dụng**.

Giá trị mặc định **không đồng nghĩa với giá trị nghiệp vụ hợp lệ**:

- `0` có thể là điểm khởi đầu phù hợp của bộ đếm.
- `0` có thể là số lượng không hợp lệ của một đơn hàng yêu cầu `quantity > 0`.
- `null` có thể hợp lệ với trường “ảnh đại diện tùy chọn”.
- `null` có thể là lỗi đối với mã khách hàng bắt buộc.

### 2.1. Có constructor thì không tự sinh default no-arg constructor nữa

~~~java
class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }
}
~~~

Vì `Ticket` đã khai báo constructor nhận `String`, compiler **không** tự sinh constructor `Ticket()`. Lệnh `new Ticket()` bị lỗi biên dịch nếu chưa khai báo thêm constructor không tham số tương ứng.

Muốn cung cấp một cách tạo mặc định hợp lệ, bạn phải định nghĩa nó:

~~~java
class Ticket {
    private final String code;

    Ticket() {
        this("UNASSIGNED");
    }

    Ticket(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Mã vé không hợp lệ");
        }
        this.code = code;
    }
}
~~~

Hai constructor là **overload** khác danh sách tham số; constructor không tham số ủy quyền sang constructor nhận `String` bằng `this("UNASSIGNED")`.

**Không nên thêm constructor rỗng `Ticket()` chỉ cho “tiện”** nếu không có bất kỳ trạng thái mặc định nào thỏa invariant. Một class đại diện cho thực thể bắt buộc có `id` thật không nên tự sinh id giả, trừ khi đó là yêu cầu nghiệp vụ rõ ràng.

## 3. Kiểm tra đầu vào ngay khi khởi tạo

**Kiểu dữ liệu đúng không đồng nghĩa giá trị hợp lệ.** `String` có thể `null` hoặc blank; `long` có thể âm; hai `LocalDate` riêng lẻ đều hợp lệ nhưng có thể tạo khoảng thời gian bị đảo. Điều kiện hợp lệ phải được xác định từ *hợp đồng của class*, không dựa vào việc `javac` chấp nhận kiểu tham số.

Ví dụ class tài khoản với mã, chủ sở hữu và số dư ban đầu:

~~~java
import java.util.Objects;

class Account {
    private final String id;
    private final String owner;
    private long balance;

    Account(String id, String owner, long openingBalance) {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(owner, "owner");
        if (id.isBlank() || owner.isBlank()) {
            throw new IllegalArgumentException("blank account info");
        }
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        this.id = id;
        this.owner = owner;
        this.balance = openingBalance;
    }
}
~~~

Đây là một **class declaration** không có `main`. Các phép kiểm tra xảy ra trước khi gán state; mọi lời gọi constructor **hoàn tất bình thường** đều tạo Account có mã/chủ không blank và balance không âm.

### Kiểm tra mối quan hệ giữa tham số

~~~java
import java.time.LocalDate;
import java.util.Objects;

class BookingPeriod {
    private final LocalDate start;
    private final LocalDate end;

    BookingPeriod(LocalDate start, LocalDate end) {
        this.start = Objects.requireNonNull(start, "start");
        this.end = Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end before start");
        }
    }
}
~~~

`LocalDate` là immutable. Điều kiện `end >= start` là **invariant của khoảng thời gian**, không phải của riêng từng `LocalDate`. Một constructor không đạt điều kiện sẽ throw thay vì trả instance hợp lệ cho caller; các assignment thực hiện trước throw trong ví dụ này không có tác dụng đưa một instance thành công ra ngoài.

**Ranh giới học tập:** ở bài này, validation minh họa *vai trò bảo vệ invariant*. Các quyết định chi tiết hơn như loại exception, chuẩn hóa, defensive copy, rollback side effects và xử lý lỗi của caller thuộc bài riêng **“Kiểm tra dữ liệu và xử lý lỗi trong hàm khởi tạo”**. Chỉ cần nhớ: **xác định invariant → kiểm tra dữ liệu phù hợp → hoàn tất khởi tạo hợp lệ hoặc báo lỗi rõ ràng**.

## 4. Thiết lập mọi field bắt buộc, ưu tiên `final` khi hợp lý

Một object dễ được hiểu và bảo trì hơn nếu các thuộc tính **không thay đổi sau khi tạo** được khai báo `final`:

~~~java
class Course {
    private final String courseCode;
    private final int credits;

    Course(String courseCode, int credits) {
        if (courseCode == null || courseCode.isBlank()) {
            throw new IllegalArgumentException("Mã học phần không hợp lệ");
        }
        if (credits < 1 || credits > 10) {
            throw new IllegalArgumentException("Số tín chỉ ngoài phạm vi");
        }

        this.courseCode = courseCode;
        this.credits = credits;
    }
}
~~~

`final` đối với field:

- Yêu cầu gán **chính xác một lần** theo các quy tắc definite assignment nếu là *blank final field*.
- Ngăn method sau khi tạo object gán lại field đó.
- Giúp biểu thị ý định “mã học phần và số tín chỉ của instance này là cố định”.

`final` **không tự kiểm tra giá trị hợp lệ**. `final String code = null;` vẫn có thể biên dịch; invariant “code không null” cần được thực thi riêng.

Với reference field, `final` cũng **không làm object được tham chiếu trở thành immutable**. `final List<String> names` không thể bị gán sang list khác, nhưng bản thân list có thể bị thay đổi nếu nó là một mutable list và có code giữ được tham chiếu.

### 4.1. Blank final field phải được gán trên các đường constructor kết thúc bình thường

~~~java
class Range {
    private final int min;
    private final int max;

    Range(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min lớn hơn max");
        }
        this.min = min;
        this.max = max;
    }
}
~~~

Constructor ném exception trước khi gán thì **không kết thúc bình thường**, nên không xuất hiện object `Range` đã khởi tạo thành công với final field chưa được gán. Nếu constructor hoàn tất, cả hai field bắt buộc đã có giá trị.

Một nhánh `if` chỉ gán `min` rồi để constructor hoàn tất mà không gán `max` sẽ gây lỗi definite assignment, nếu `max` là blank final field. Lỗi compiler giúp phát hiện một số đường khởi tạo thiếu dữ liệu, nhưng **không thể thay thế kiểm tra nghiệp vụ** như `min <= max`.

## 5. Tránh cập nhật một phần trước khi kiểm tra xong

Khi constructor tạo nhiều thành phần, nên thực hiện validation và tính toán có thể thất bại **trước khi xuất bản đối tượng**. Với class bình thường, nếu constructor ném exception, biểu thức `new` không trả về tham chiếu hoàn chỉnh cho caller; nhưng cập nhật các đối tượng bên ngoài hoặc làm lộ `this` vẫn có thể gây hậu quả.

Ví dụ thiết kế có tác dụng phụ nguy hiểm:

~~~java
import java.util.List;

class BadRegistration {
    BadRegistration(List<String> externalLog, String username) {
        externalLog.add("starting"); // Đã sửa trạng thái của caller
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username không hợp lệ");
        }
    }
}
~~~

Đây là đoạn minh họa. Nếu `username` sai, constructor ném exception nhưng `externalLog` đã bị sửa. **Không thể kết luận “constructor thất bại thì mọi side effect đều tự rollback”**.

Một thiết kế dễ dự đoán hơn:

~~~java
import java.util.List;

class Registration {
    private final String username;

    Registration(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username không hợp lệ");
        }
        this.username = username;
    }
}
~~~

Nếu thật sự phải gọi resource bên ngoài hoặc lưu dữ liệu ở thời điểm tạo, hãy thiết kế giao dịch, cleanup, rollback và trách nhiệm sở hữu riêng. Constructor không tự tạo transaction trên database hay tự hoàn tác các thao tác I/O.

### 5.1. Tính trước giá trị mới có thể tràn số

~~~java
class AmountSummary {
    private final long total;

    AmountSummary(long subtotal, long tax) {
        if (subtotal < 0 || tax < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }
        long checkedTotal = Math.addExact(subtotal, tax);
        this.total = checkedTotal;
    }
}
~~~

`Math.addExact` ném `ArithmeticException` nếu `long` bị tràn. Nhờ thực hiện phép tính trước khi gán field `total`, constructor chỉ kết thúc thành công khi tổng biểu diễn được trong `long`. Đây là một ví dụ cần thiết của **trạng thái hợp lệ không chỉ là từng đối số hợp lệ**.

## 6. Defensive copy: ngăn caller sửa dữ liệu sau khi constructor kết thúc

Một lỗi thường gặp là constructor kiểm tra mutable input nhưng vẫn giữ **tham chiếu gốc** do caller sở hữu. Sau khi object được tạo, caller thay đổi dữ liệu đầu vào và phá invariant.

**Ví dụ không an toàn:**

~~~java
import java.util.List;

class UnsafeEnrollment {
    private final List<String> courseCodes;

    UnsafeEnrollment(List<String> codes) {
        if (codes == null || codes.isEmpty()) {
            throw new IllegalArgumentException("Phải chọn ít nhất một môn");
        }
        this.courseCodes = codes; // Giữ mutable list do caller nắm giữ
    }
}
~~~

Caller có thể viết:

~~~java
List<String> chosen = new java.util.ArrayList<>();
chosen.add("JAVA");
UnsafeEnrollment enrollment = new UnsafeEnrollment(chosen);
chosen.clear(); // object bên trong có thể mất dữ liệu đã validate
~~~

Đoạn này là fragment trong method, không chạy độc lập. `final` chỉ chặn gán lại field `courseCodes`, **không chặn `chosen.clear()` sửa object list dùng chung**.

### 6.1. Chụp bản sao bất biến khi dữ liệu là collection của phần tử immutable

~~~java
import java.util.List;

class Enrollment {
    private final List<String> courseCodes;

    Enrollment(List<String> codes) {
        if (codes == null || codes.isEmpty()) {
            throw new IllegalArgumentException("Phải chọn ít nhất một môn");
        }

        List<String> snapshot = List.copyOf(codes);

        for (String code : snapshot) {
            if (code.isBlank()) {
                throw new IllegalArgumentException("Mã môn không hợp lệ");
            }
        }

        this.courseCodes = snapshot;
    }

    List<String> getCourseCodes() {
        return courseCodes;
    }
}
~~~

`List.copyOf` (Java 10+) tạo một danh sách **không thể sửa qua các method thay đổi list**, không chấp nhận phần tử `null`, và bảo vệ khỏi các thay đổi cấu trúc về sau trên một nguồn mutable như `ArrayList`. Ở đây phần tử là `String` immutable, nên việc trả danh sách đó qua getter không cho caller sửa nội dung phần tử.

Lưu ý:

- `List.copyOf(codes)` ném `NullPointerException` nếu trong `codes` có phần tử null. Nếu hợp đồng muốn chuyển trường hợp đó thành `IllegalArgumentException` với thông báo riêng, hãy kiểm tra trước hoặc bắt/xử lý có chủ đích.
- `List.copyOf` là **sao chép nông về mặt phần tử**: đối với `List<MutableItem>`, bản sao vẫn chứa tham chiếu đến các `MutableItem`. Nếu phần tử mutable, phải sao chép/đóng băng từng phần tử theo yêu cầu.
- Không nên gọi cùng một mutable `codes` nhiều lần vừa validate vừa copy nếu một thread khác có thể sửa nó đồng thời. Trong môi trường concurrency, cần có hợp đồng rằng caller không thay đổi list trong lúc xây dựng, hoặc cơ chế đồng bộ/snapshot nhất quán thích hợp.
- Đừng dùng `Collections.unmodifiableList(codes)` rồi mặc nhiên coi đó là snapshot. Nó chỉ là **view không cho sửa qua view**; thay đổi ở nguồn `codes` có thể vẫn được quan sát.

### 6.2. Với mảng, clone dữ liệu đầu vào khi cần sở hữu độc lập

~~~java
class ExamResult {
    private final int[] marks;

    ExamResult(int[] marks) {
        if (marks == null || marks.length == 0) {
            throw new IllegalArgumentException("Thiếu điểm");
        }

        int[] copy = marks.clone();
        for (int mark : copy) {
            if (mark < 0 || mark > 100) {
                throw new IllegalArgumentException("Điểm ngoài [0,100]");
            }
        }
        this.marks = copy;
    }

    int[] getMarks() {
        return marks.clone();
    }
}
~~~

Đây là đoạn khai báo. Mỗi phần tử `int` là primitive, nên `clone()` của mảng tạo bản sao độc lập về các giá trị điểm. Copy khi **nhận vào** chống sửa nguồn sau constructor; copy khi **trả ra** chống caller sửa mảng nội bộ qua getter. Nếu mảng chứa object mutable, `clone()` chỉ sao chép tham chiếu phần tử, cần tiếp tục cân nhắc deep copy.

## 7. Ví dụ hoàn chỉnh: constructor tạo một đối tượng luôn hợp lệ

Chương trình sau kết hợp **validation**, **field `final`**, **defensive copy**, **constructor overloading/chaining** và chứng minh dữ liệu nguồn bị thay đổi sau khi tạo **không phá trạng thái của object**.

Lưu thành **`ValidConstructionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidConstructionDemo {
    static final class Enrollment {
        private final String studentId;
        private final List<String> courseCodes;
        private final int maximumCourses;

        Enrollment(String studentId, List<String> courseCodes) {
            this(studentId, courseCodes, 4);
        }

        Enrollment(String studentId,
                   List<String> courseCodes,
                   int maximumCourses) {
            if (studentId == null || studentId.isBlank()) {
                throw new IllegalArgumentException("Mã sinh viên không hợp lệ");
            }
            if (maximumCourses < 1) {
                throw new IllegalArgumentException("Giới hạn phải dương");
            }
            if (courseCodes == null) {
                throw new IllegalArgumentException("Danh sách môn bị null");
            }

            List<String> copy = List.copyOf(courseCodes);

            if (copy.isEmpty() || copy.size() > maximumCourses) {
                throw new IllegalArgumentException(
                        "Số môn không hợp lệ");
            }
            for (String code : copy) {
                if (code.isBlank()) {
                    throw new IllegalArgumentException(
                            "Mã môn không hợp lệ");
                }
            }
            if (copy.stream().distinct().count() != copy.size()) {
                throw new IllegalArgumentException(
                        "Trùng mã môn");
            }

            this.studentId = studentId;
            this.courseCodes = copy;
            this.maximumCourses = maximumCourses;
        }

        String studentId() {
            return studentId;
        }

        List<String> courseCodes() {
            return courseCodes;
        }

        int capacityLeft() {
            return maximumCourses - courseCodes.size();
        }
    }

    public static void main(String[] args) {
        List<String> chosen = new ArrayList<>(
                List.of("JAVA", "SQL"));

        Enrollment registration = new Enrollment("SV-17", chosen);

        chosen.clear();
        chosen.add("PYTHON");

        System.out.println("Student = " + registration.studentId());
        System.out.println("Courses = " + registration.courseCodes());
        System.out.println("Capacity left = " + registration.capacityLeft());

        try {
            new Enrollment("SV-18", List.of("JAVA", "JAVA"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        try {
            registration.courseCodes().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot edit courses");
        }

        System.out.println("Still valid = "
                + registration.courseCodes());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 ValidConstructionDemo.java
java ValidConstructionDemo
~~~

**Stdout chính xác:**

~~~text
Student = SV-17
Courses = [JAVA, SQL]
Capacity left = 2
Rejected = Trùng mã môn
Cannot edit courses
Still valid = [JAVA, SQL]
~~~

Giải thích:

1. Constructor hai tham số gọi `this(studentId, courseCodes, 4)`, giúp **tập trung toàn bộ validation tại một constructor chính**. Giới hạn mặc định là 4 môn.
2. Constructor chính kiểm tra id, capacity và `courseCodes`; tạo `List.copyOf`; kiểm tra số lượng, mã môn blank, mã trùng rồi mới gán ba field `final`.
3. Sau khi tạo `registration`, caller gọi `chosen.clear()` và thêm `"PYTHON"` vào list ban đầu. Vì constructor đã giữ snapshot, `registration.courseCodes()` vẫn là `[JAVA, SQL]`.
4. `capacityLeft()` trả `4 - 2 = 2`.
5. Tạo `Enrollment("SV-18", List.of("JAVA", "JAVA"))` vi phạm invariant “mã môn không trùng”, nên constructor ném `IllegalArgumentException` với message `"Trùng mã môn"`; không trả về một instance hoàn chỉnh cho caller.
6. Gọi `clear()` lên danh sách trả về thất bại với `UnsupportedOperationException` vì danh sách giữ nội bộ là không sửa được; object vẫn giữ trạng thái hợp lệ.

**Giới hạn minh họa:** đây là ví dụ cho collection của `String` immutable. Với tập các `Course` mutable, chỉ `List.copyOf` chưa đủ chống sửa từng object phần tử. Nếu đặt ra invariant liên quan nội dung object con, cần mô hình hóa bất biến sâu hoặc kiểm soát ownership thích hợp.

## 8. Constructor chaining: không lặp validation giữa nhiều cách tạo

Class có thể có nhiều constructor (constructor overloading), mỗi constructor cung cấp một cách khởi tạo. Để tránh những cách tạo dẫn đến trạng thái bất nhất, nên **ủy quyền về một constructor trung tâm**:

~~~java
class Coordinate {
    private final int x;
    private final int y;

    Coordinate() {
        this(0, 0);
    }

    Coordinate(int position) {
        this(position, position);
    }

    Coordinate(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Đây là đoạn khai báo lớp. Hai constructor đầu gọi constructor hai tham số bằng `this(...)`, nên logic thiết lập trạng thái không bị sao chép ở ba nơi.

### 8.1. Quy tắc của `this(...)` và `super(...)` trong Java 17

- `this(...)` gọi **constructor khác cùng class**.
- `super(...)` gọi **constructor của superclass**.
- Với Java 17, lời gọi constructor tường minh `this(...)` hoặc `super(...)` phải nằm **đầu thân constructor**, và một constructor không thể dùng cả hai lời gọi tường minh như hai bước liên tiếp.
- Nếu không có lời gọi tường minh phù hợp, constructor sẽ có lời gọi `super()` ngầm theo các quy tắc của Java. Nếu superclass không có constructor không tham số truy cập được, subclass phải chỉ rõ constructor superclass có thể gọi.
- Chuỗi gọi `this(...)` không được tạo vòng lặp đệ quy constructor.

Mục tiêu của constructor chaining là thống nhất đường khởi tạo hợp lệ, **không chỉ giảm số dòng code**. Một constructor tiện lợi không nên bỏ qua các kiểm tra bắt buộc mà constructor chính thực hiện.

### 8.2. Constructor superclass cũng tham gia tạo trạng thái hợp lệ

~~~java
class Document {
    private final String id;

    Document(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        this.id = id;
    }
}

class Invoice extends Document {
    private final long amount;

    Invoice(String id, long amount) {
        super(id);
        if (amount < 0) {
            throw new IllegalArgumentException("amount âm");
        }
        this.amount = amount;
    }
}
~~~

Đây là đoạn khai báo; không có `main`. Constructor `Invoice` gọi `super(id)` để superclass xác lập invariant của `Document` rồi mới xác lập phần invariant bổ sung của `Invoice`. Nếu superclass từ chối `id`, constructor subclass không hoàn tất.

Trong thực hành OOP, việc gọi method có thể bị override trong constructor superclass là **nguy hiểm**: dynamic dispatch có thể chạy implementation của subclass khi field của subclass vẫn đang ở giá trị mặc định. Để giữ trạng thái nhất quán, nên tránh gọi overridable instance methods từ constructor, nhất là nếu implementation cần field chưa khởi tạo.

## 9. Khác biệt giữa field initializer, instance initializer và constructor body

Java hỗ trợ nhiều nơi đặt logic khởi tạo:

~~~java
class Settings {
    private int retries = 3;

    {
        retries += 1;
    }

    Settings(int retries) {
        if (retries < 0) {
            throw new IllegalArgumentException("retries âm");
        }
        this.retries = retries;
    }
}
~~~

Trong class này:

1. Instance field có giá trị mặc định `0` khi vùng nhớ object được khởi tạo.
2. Field initializer đặt `retries = 3` khi đến lượt khởi tạo của class.
3. Instance initializer block chạy theo thứ tự văn bản tương ứng, tăng `retries` lên `4`.
4. Constructor body tiếp tục và gán `this.retries` từ tham số đã validate.

Nếu gọi `new Settings(7)`, giá trị cuối `retries` là 7. **Không nên viết logic khởi tạo rải rác nhiều nơi nếu khiến invariant khó suy luận**. Một constructor trung tâm thường dễ đọc hơn, trừ khi initializer giúp khai báo một mặc định chung rất rõ ràng.

### 9.1. Constructor không tự động thực thi lại khi field thay đổi

Sau khi tạo object, gọi setter/command không chạy lại constructor. Vì vậy invariant được thiết lập bởi constructor phải được **tiếp tục duy trì** qua các method thay đổi trạng thái:

~~~java
class ProductStock {
    private int quantity;

    ProductStock(int quantity) {
        requireNonNegative(quantity);
        this.quantity = quantity;
    }

    void replenish(int added) {
        if (added <= 0) {
            throw new IllegalArgumentException("added phải dương");
        }
        quantity = Math.addExact(quantity, added);
    }

    int quantity() {
        return quantity;
    }

    private static void requireNonNegative(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("quantity âm");
        }
    }
}
~~~

Đây là đoạn khai báo. Nếu cho phép một setter `setQuantity(-99)` không validation, object vẫn có thể đi vào trạng thái sai sau khi constructor thành công. **Invariant là hợp đồng suốt vòng đời**, không chỉ kiểm tra tại khoảnh khắc `new`.

## 10. Không để `this` thoát ra trong khi constructor chưa hoàn tất

Một rủi ro khó thấy là **this escape**: constructor công bố tham chiếu đến object đang được tạo cho code khác trước khi hoàn tất việc khởi tạo. Khi đó bên ngoài có thể quan sát các field chưa được thiết lập.

Ví dụ thiết kế cần tránh:

~~~java
import java.util.List;

class EventListener {
    private final String label;

    EventListener(List<EventListener> registry) {
        registry.add(this);  // Lộ tham chiếu quá sớm
        this.label = "ready";
    }
}
~~~

Ở đây `registry` là collection do caller sở hữu. Constructor đưa `this` vào danh sách **trước khi gán `label`**, khiến callback, observer hoặc một thread khác có thể nhìn thấy một instance đang trong quá trình xây dựng. Nếu constructor thất bại sau đó, registry cũng có thể giữ tham chiếu đến object không hoàn chỉnh.

Cách thiết kế an toàn hơn là tạo hoàn chỉnh trước rồi đăng ký:

~~~java
import java.util.List;

class EventListener {
    private final String label;

    EventListener(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("label không hợp lệ");
        }
        this.label = label;
    }

    static EventListener createAndRegister(
            String label, List<EventListener> registry) {
        EventListener ready = new EventListener(label);
        registry.add(ready);
        return ready;
    }
}
~~~

Đây là đoạn khai báo. Factory tạo object đã hoàn tất constructor rồi mới thêm vào registry. Cần kiểm soát thêm điều kiện `registry != null` và tính thread-safe của registry theo hợp đồng thực tế. Nếu đăng ký là một giao dịch nhiều bước, vẫn phải xác định chiến lược rollback khi registry ném exception.

Các dạng *this escape* khác cần cảnh giác:

- Truyền `this` cho một API bên ngoài có thể lưu tham chiếu hoặc gọi callback ngay.
- Đăng ký listener trong constructor khi listener có thể bị kích hoạt trước lúc khởi tạo xong.
- Tạo/start thread trong constructor và để task sử dụng `this`.
- Gọi overridable method từ constructor; implementation subclass có thể quan sát field subclass chưa được khởi tạo.

**Chỉ vì field có `final` không có nghĩa mọi cách công bố đối tượng đều an toàn**. Các bảo đảm đặc biệt của final fields trong Java Memory Model phụ thuộc việc object được xây dựng đúng cách, bao gồm không để tham chiếu tới object thoát ra trong lúc đang xây dựng. Nếu object mutable được chia sẻ giữa thread, vẫn cần cơ chế safe publication và synchronization thích hợp.

## 11. Kế thừa và thứ tự khởi tạo: tránh dựa vào subclass quá sớm

Xét đoạn minh họa sau:

~~~java
class Parent {
    Parent() {
        describe();
    }

    void describe() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String value = "ready";

    @Override
    void describe() {
        System.out.println(value);
    }
}
~~~

Nếu một chương trình tạo `new Child()`, constructor của `Parent` có thể gọi implementation `Child.describe()` do dynamic dispatch. Nhưng lúc đó field initializer `value = "ready"` của `Child` **chưa chạy**, nên `value` vẫn ở mặc định `null`. Đây không phải cách an toàn để superclass validate trạng thái của subclass.

Nên làm:

- Constructor superclass chỉ thiết lập và kiểm tra **phần trạng thái do superclass sở hữu**.
- Tránh gọi overridable methods trong constructor; ưu tiên private, static hoặc final methods khi cần helper không phụ thuộc vào subclass.
- Subclass gọi `super(...)` hợp lệ, sau đó thiết lập và kiểm tra phần trạng thái riêng.
- Nếu cần thao tác yêu cầu object hoàn chỉnh, thực hiện sau khi constructor kết thúc trong factory hoặc phương thức khởi động có hợp đồng rõ ràng.

Một bất biến dùng chung giữa superclass và subclass có thể cần thiết kế API bảo vệ hơn là cố gọi method override để “kiểm tra một lần cho tất cả”.

## 12. Record và compact constructor trong Java 17

**Record** là lựa chọn phù hợp để khai báo một kiểu dữ liệu mang giá trị với các thành phần được xác định rõ. Record không làm validation tự xuất hiện, nhưng cho phép **compact constructor** để kiểm tra bất biến súc tích:

~~~java
import java.util.Objects;

record DateRange(String start, String end) {
    DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (start.compareTo(end) > 0) {
            throw new IllegalArgumentException("start sau end");
        }
    }
}
~~~

Đây là đoạn khai báo record, không có `main`. Chỉ số so sánh chuỗi ISO ngày sẽ đúng về thứ tự khi dữ liệu có định dạng chuẩn tương ứng, nhưng ứng dụng thực tế nên dùng `LocalDate` thay vì các chuỗi ngày tự do.

Ví dụ idiomatic hơn:

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {
    DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end trước start");
        }
    }
}
~~~

Với compact constructor, Java sẽ thực hiện việc gán các record components cho field tương ứng **sau phần thân compact constructor** theo quy tắc ngôn ngữ. Vì vậy, bên trong khối này hãy kiểm tra/chỉnh tham số nếu thật sự cần; không cố gán trực tiếp các component fields như constructor thường.

Record cung cấp các field component final và accessor, nhưng **không đảm bảo deep immutability** cho thành phần tham chiếu mutable. Ví dụ record chứa `List<String>` vẫn nên dùng `List.copyOf` nếu cần snapshot và không cho sửa danh sách.

## 13. Constructor thất bại: có còn đối tượng nào được sử dụng không?

Giả sử:

~~~java
class PositiveQuantity {
    private final int quantity;

    PositiveQuantity(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        this.quantity = quantity;
    }
}
~~~

Khi caller thực hiện `new PositiveQuantity(-1)`, exception làm biểu thức tạo đối tượng thất bại; caller **không nhận được tham chiếu trả về bình thường** từ biểu thức `new` đó.

Nhưng hãy phân biệt các tác động:

- **Không có kết quả khởi tạo thành công**: đúng cho lời gọi `new` ném exception.
- **Không có tác dụng phụ nào đã xảy ra**: không được bảo đảm. Constructor vẫn có thể đã ghi log, sửa collection ngoài, mở resource, gọi service hoặc làm lộ `this` trước khi ném.
- **Các field đã gán trước khi ném vẫn được rollback**: Java không áp dụng transaction tự động cho các field hoặc tài nguyên ngoài.
- **Garbage collector tự xử lý mọi resource ngoài bộ nhớ**: không đúng; resource như file handle, socket và transaction cần cleanup phù hợp, thường qua `try`/`finally` hoặc `try-with-resources` ở điểm sở hữu.

### 13.1. Cân nhắc static factory nếu việc tạo cần nhiều bước

Constructor phù hợp với logic đồng bộ, rõ ràng: validate đầu vào và gán trạng thái. Nếu quá trình xây dựng cần I/O, tra cứu từ database, mở resource, cấu hình phức tạp hoặc thực hiện hành động có thể rollback, một **static factory** hoặc service tạo object thường dễ tổ chức hơn:

~~~java
class ApiClient {
    private final String endpoint;

    private ApiClient(String endpoint) {
        this.endpoint = endpoint;
    }

    static ApiClient fromEndpoint(String endpoint) {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("endpoint không hợp lệ");
        }
        return new ApiClient(endpoint);
    }
}
~~~

Đây là đoạn khai báo minh họa; ở đây static factory chỉ validate rồi gọi private constructor, chưa có I/O. Nó cho phép đặt tên cách tạo (`fromEndpoint`), phối hợp validation hoặc lựa chọn implementation khi cần. **Factory không thay thế invariant**: constructor/factory vẫn phải đảm bảo mọi object được công bố là hợp lệ.

Cân nhắc thiết kế để caller không có đường `new` công khai bỏ qua validation nếu class thực sự cần một quy trình tạo tập trung.

## 14. Constructor và kiểm soát khả năng tạo object

Mức truy cập constructor quy định những nơi được phép gọi nó:

| Khai báo | Ý nghĩa điển hình |
| --- | --- |
| `public ClassName(...)` | Có thể tạo từ nơi truy cập được class/constructor |
| `protected ClassName(...)` | Dành cho mô hình kế thừa và truy cập theo quy tắc protected |
| `ClassName(...)` không modifier | Chỉ được gọi theo phạm vi package-private |
| `private ClassName(...)` | Kiểm soát việc tạo trong phạm vi class/nested contexts hợp lệ; thường đi cùng static factory |

Một class có thể có constructor `private` và các factory `public static` để bảo đảm caller luôn đi qua quy trình kiểm tra được kiểm soát. Ngược lại, công khai tất cả constructor overload nhưng mỗi overload validate khác nhau dễ tạo **nhiều đường đi tới trạng thái không nhất quán**.

Không có kiểu trả về trong constructor. Ví dụ:

~~~java
class Device {
    Device() { }       // constructor

    void Device(int n) { } // đây là method tên Device, KHÔNG phải constructor
}
~~~

Đây là khai báo lớp hợp lệ về mặt cú pháp, nhưng method `void Device(int n)` thường là lỗi thiết kế do người học viết nhầm. Constructor thực sự cần **tên class**, **không có return type**; phân biệt này quan trọng khi debug các field “không được khởi tạo như kỳ vọng”.

## 15. Khi constructor không phải con đường duy nhất tạo/khôi phục object

Một class có thể được tạo hoặc khôi phục qua những cơ chế ngoài lời gọi `new` thông thường. Ví dụ, Java Object Serialization có quy tắc riêng: khi deserialize một lớp `Serializable` thông thường, constructor và instance initializer **của chính lớp Serializable đó** không chạy như cách khởi tạo bằng `new`; constructor không tham số của superclass gần nhất không Serializable được thực hiện theo quy tắc serialization.

Vì thế, nếu class có bất biến quan trọng và tham gia serialization, cần thiết kế cách bảo vệ invariant khi khôi phục:

- Kiểm tra dữ liệu đã khôi phục trong logic phù hợp (ví dụ `readObject`) hoặc dùng serialization proxy pattern khi thích hợp.
- Không giả định constructor luôn chạy đối với mọi object được deserialize.
- Cân nhắc nguy cơ an toàn của native Java deserialization từ nguồn không tin cậy; không dùng bừa bãi `ObjectInputStream` với byte stream tùy ý.
- Framework persistence/ORM, reflection hoặc các cơ chế object mapping khác có thể có quy tắc tạo object riêng, cần tuân thủ hợp đồng của framework. Đừng vì đáp ứng framework mà công khai constructor tạo trạng thái sai cho mọi caller nếu có cách cấu hình an toàn hơn.

Đây là **giới hạn của invariant chỉ dựa vào constructor**. Trong code Java thông thường tạo bằng `new`, validation ở constructor là tuyến phòng thủ đầu tiên; với cơ chế khôi phục/ánh xạ riêng, cần bảo vệ thêm các đường vào khác.

## 16. Constructor, immutability và thread safety

Một class có mọi field `private final`, sử dụng kiểu immutable và phòng thủ các mutable input có thể giảm đáng kể số trạng thái cần theo dõi:

~~~java
import java.util.List;

class CoursePlan {
    private final String name;
    private final List<String> codes;

    CoursePlan(String name, List<String> codes) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name trống");
        }
        this.codes = List.copyOf(codes);
        if (this.codes.isEmpty()) {
            throw new IllegalArgumentException("codes rỗng");
        }
        this.name = name;
    }

    String name() {
        return name;
    }

    List<String> codes() {
        return codes;
    }
}
~~~

Đây là đoạn minh họa. Với String/list-of-String, sau khi constructor thành công, object không có method sửa trạng thái và không làm lộ collection mutable của nó. Thiết kế như vậy rất thuận lợi cho việc chia sẻ dữ liệu.

Nhưng:

- **`final` không tự bảo đảm an toàn đồng thời cho object mutable được trỏ tới.**
- Nếu constructor làm lộ `this` quá sớm, các bảo đảm của final fields và safe initialization có thể bị phá.
- Nếu object có field mutable hoặc liên quan dữ liệu thay đổi giữa các thread, cần cơ chế synchronization/safe publication thích hợp.
- Nếu object được tạo từ input bị một thread khác sửa đồng thời không có hợp đồng đồng bộ, constructor không tự bảo đảm snapshot nguyên tử.

**Tạo đúng trạng thái ban đầu** và **duy trì tính đúng đắn khi nhiều thread sử dụng** là hai trách nhiệm liên quan nhưng không đồng nhất.

## 17. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Constructor chỉ gán field, không validate | Object có `null`, số âm, quan hệ field mâu thuẫn | Xác định invariant và kiểm tra trước khi gán |
| Cho mọi class constructor không tham số dù không có mặc định hợp lệ | Caller tạo object chưa sẵn sàng sử dụng | Chỉ cho phép cách tạo tạo ra trạng thái hợp lệ |
| Nghĩ field có giá trị default là hợp lệ | `int = 0`, reference = `null` có thể sai nghiệp vụ | Phân biệt default của Java với điều kiện miền dữ liệu |
| Dùng `final` để thay validation | Final field vẫn có thể nhận giá trị vô nghĩa | Vừa validate vừa gán `final` |
| Giữ tham chiếu đến mutable input | Caller sửa input sau constructor làm phá invariant | Defensive copy hoặc chuyển quyền sở hữu có hợp đồng rõ |
| Trả trực tiếp mảng/list mutable của object | Caller sửa trạng thái bên trong ngoài command | Getter trả snapshot/read-only data thích hợp |
| Copy nông rồi nghĩ các object phần tử immutable | Phần tử mutable vẫn chia sẻ | Xem xét deep copy hoặc immutable value objects |
| Hai constructor overload có quy tắc validation khác nhau | Một đường tạo hợp lệ, đường khác lọt dữ liệu sai | Dùng `this(...)` hướng đến constructor trung tâm |
| Gọi overridable method từ constructor | Subclass method có thể thấy field chưa khởi tạo | Tránh virtual dispatch trong constructor |
| Đăng ký `this` vào listener/registry khi chưa hoàn tất | Object dở dang bị code khác quan sát | Đăng ký sau khi tạo, thường qua factory |
| Constructor ném lỗi sau khi sửa tài nguyên ngoài | Side effect còn lại dù `new` thất bại | Validate trước, cleanup/transaction rõ ràng |
| Constructor overload quá nhiều tham số cùng kiểu | Caller dễ đảo vị trí đối số | Dùng value object, builder/factory có tên, validation |
| Setter công khai phá bất biến sau constructor | Object hợp lệ ban đầu nhưng sai ở giai đoạn sau | Command phải duy trì invariant |
| Dựa vào constructor để bảo vệ cả deserialization | Một số cơ chế khôi phục không chạy constructor như `new` | Bảo vệ cả đường khôi phục/ánh xạ dữ liệu |

### 17.1. Một tình huống dễ sai: kiểm tra xong rồi vẫn giữ danh sách cũ

~~~java
class UnsafeSet {
    private final java.util.List<String> names;

    UnsafeSet(java.util.List<String> names) {
        if (names == null || names.isEmpty()) {
            throw new IllegalArgumentException();
        }
        this.names = names; // invariant "không rỗng" không được bảo vệ lâu dài
    }
}
~~~

Đây là đoạn minh họa. Dù constructor đã validate, sau đó caller gọi `names.clear()` khiến field nội bộ trỏ đến list rỗng. **Validation chỉ thật sự giữ được hiệu lực khi thiết kế quyền sở hữu/khả năng thay đổi đi cùng nó**.

## 18. Bài tập tự kiểm tra

**Câu 1.** Tại sao `new Student(null, -5)` có thể biên dịch dù không hợp lệ về nghiệp vụ?

**Đáp án:** Compiler chỉ kiểm tra tham số có kiểu tương thích (null là giá trị tham chiếu và `-5` là `int`). Quy tắc “mã sinh viên không null” hoặc “tuổi không âm” là invariant cần constructor kiểm tra ở runtime.

**Câu 2.** `private final List<String> items` có đủ để bảo đảm caller không xóa phần tử không?

**Đáp án:** Không. `final` ngăn gán lại field tham chiếu, nhưng không ngăn thay đổi mutable list. Có thể snapshot bằng `List.copyOf` nếu hợp đồng không cho phép caller chỉnh list, đồng thời đảm bảo phần tử phù hợp.

**Câu 3.** Một class khai báo `Order(String id)` nhưng không khai báo `Order()`. `new Order()` có tự dùng constructor mặc định không?

**Đáp án:** Không. Khi class đã khai báo ít nhất một constructor, compiler không tự thêm default no-arg constructor. Muốn có phải khai báo tường minh.

**Câu 4.** Một constructor ném `IllegalArgumentException` sau khi thêm `this` vào danh sách toàn cục. Có chắc danh sách sẽ không chứa object đó không?

**Đáp án:** Không. Exception không tự rollback side effect; đó là lỗi làm lộ đối tượng chưa hoàn chỉnh (*this escape*). Tránh đăng ký object trước khi constructor hoàn tất.

**Câu 5.** Vì sao `this(...)` thường hữu ích khi class có nhiều constructor overload?

**Đáp án:** Nó tập trung validation và logic thiết lập trạng thái về một đường khởi tạo trung tâm, giảm khả năng một overload bỏ sót invariant.

**Câu 6.** Constructor superclass gọi một method overridable. Subclass override method ấy và đọc field subclass. Rủi ro gì?

**Đáp án:** Dynamic dispatch có thể gọi method subclass **trước khi các field initializer/constructor body của subclass chạy**, nên method thấy giá trị mặc định như `null` hoặc `0`. Nên tránh gọi overridable methods trong constructor.

**Câu 7.** Có phải constructor hoàn tất thì object tự động thread-safe không?

**Đáp án:** Không. Constructor thiết lập trạng thái ban đầu; tính đúng khi nhiều thread chia sẻ phụ thuộc vào mutability, safe publication, synchronization và giao thức truy cập sau đó.

**Câu 8.** Record `record Range(int min, int max)` có tự từ chối `min > max` không?

**Đáp án:** Không. Record tự sinh các thành viên theo quy tắc Java, nhưng invariant nghiệp vụ cần compact constructor hoặc constructor hợp lệ khác kiểm tra.

**Câu 9.** `List.copyOf(list)` có luôn tạo bản sao sâu của tất cả đối tượng phần tử không?

**Đáp án:** Không. Nó bảo vệ cấu trúc danh sách qua kết quả không sửa được, nhưng các object phần tử mutable vẫn có thể được chia sẻ. Cần xử lý riêng nếu invariant phụ thuộc trạng thái phần tử.

**Câu 10.** Một instance field `int quantity` mặc định bằng 0. Điều đó có nghĩa `quantity = 0` luôn hợp lệ không?

**Đáp án:** Không. Nếu nghiệp vụ yêu cầu đơn hàng chứa ít nhất một đơn vị, constructor phải từ chối 0 hoặc cung cấp cách khởi tạo mặc định thỏa điều kiện đó.

## 19. Checklist thiết kế constructor tạo trạng thái hợp lệ

Khi viết constructor mới, hãy kiểm tra theo thứ tự:

1. **Định nghĩa invariant:** object sau khi tạo thành công phải luôn có những tính chất nào?
2. **Kiểm tra từng tham số:** null, blank, khoảng giá trị, định dạng, độ dài và các điều kiện khác.
3. **Kiểm tra quan hệ tham số:** `start <= end`, tổng không tràn, số phần tử trong giới hạn, không trùng theo yêu cầu.
4. **Quyết định field `final`:** giá trị nào không nên gán lại sau khi khởi tạo?
5. **Đánh giá mutable input:** giữ tham chiếu, copy nông, copy sâu hay chuyển quyền sở hữu có hợp đồng rõ?
6. **Chỉ thiết lập state đã xác thực:** ưu tiên tính toán/snapshot trước khi gán hoặc tạo side effect không thể hoàn tác.
7. **Thống nhất các constructor overload:** dùng `this(...)` và `super(...)` đúng quy tắc; tránh các đường bỏ qua validation.
8. **Không công bố `this` quá sớm:** tránh callback/registry/thread sử dụng instance chưa hoàn chỉnh.
9. **Bảo đảm exception behavior:** constructor thất bại không để lại tài nguyên hoặc tác động ngoài bị bỏ quên.
10. **Bảo vệ toàn bộ vòng đời:** mọi method thay đổi trạng thái về sau phải duy trì invariant, không chỉ constructor.
11. **Xem xét các đường khôi phục khác:** serialization, ORM hoặc framework mapping nếu ứng dụng dùng chúng.
12. **Viết test:** constructor hợp lệ tạo object dùng được; đầu vào sai bị từ chối; sửa nguồn mutable sau khi tạo không phá invariant.

**Kết luận:** một constructor tốt là **cửa vào kiểm soát trạng thái của class**. Nó không chỉ “điền dữ liệu vào field”, mà làm rõ ngay tại lúc tạo object: *đầu vào nào được chấp nhận, quan hệ field nào phải đúng, dữ liệu nào được sở hữu độc lập và đối tượng có thể được công bố an toàn từ thời điểm nào*. Khi kết hợp constructor validation với đóng gói và các command duy trì invariant, class trở nên dễ sử dụng đúng và khó rơi vào trạng thái không hợp lệ.
