# Thu thập tình huống sử dụng và quy tắc nghiệp vụ để mô hình hóa OOP

**Mục tiêu:** Đi từ câu chuyện của người dùng đến **use case**, **business rule**, **điều kiện bất biến**, rồi mới xác định trách nhiệm của đối tượng và xây dựng Java API có thể kiểm thử. Bài học dùng ví dụ **sinh viên đăng ký khóa học**; các quy tắc trong ví dụ là giả định minh họa, không phải luật áp dụng mặc định cho mọi nền tảng đào tạo.

## 1. Vì sao phải thu thập trước khi thiết kế lớp?

Một yêu cầu ban đầu thường rất ngắn:

> “Sinh viên muốn đăng ký một khóa học. Hệ thống báo thành công nếu đăng ký được.”

Nếu bắt đầu ngay bằng lớp `Student`, `Course`, `EnrollmentService`, `Database`, ta dễ bỏ qua những câu hỏi quyết định hành vi:

- Sinh viên chưa được kích hoạt tài khoản có thể đăng ký không?
- Khóa học đã đóng đăng ký thì sao?
- Phải hoàn thành môn tiên quyết trước hay có ngoại lệ?
- Có được đăng ký cùng một khóa hai lần?
- Nếu chỗ cuối cùng được hai người chọn đồng thời, ai nhận chỗ?
- Khi thành công, phải lưu thông tin nào và trả gì cho người dùng?
- Nếu gửi email thông báo lỗi, đăng ký có còn thành công không?
- Ai có quyền thay đổi sức chứa, thời hạn, danh sách môn tiên quyết?

**Use case** mô tả một mục tiêu mà **actor** đạt được nhờ tương tác với hệ thống. **Business rule** diễn tả điều kiện, chính sách hoặc ràng buộc của tổ chức mà các use case phải tuân thủ. Hai thứ bổ sung nhau:

- Use case trả lời: **Ai làm gì, để đạt mục tiêu nào, theo các luồng nào?**
- Business rule trả lời: **Trong điều kiện nào hệ thống được hoặc không được làm việc đó?**
- Domain model trả lời: **Những khái niệm nào tồn tại, giữ trạng thái gì và chịu trách nhiệm bảo vệ điều kiện nào?**

Đừng suy luận rằng mỗi danh từ trong yêu cầu trở thành một class, hoặc mỗi dòng use case trở thành một method. Mô hình hóa là bước chuyển từ ngôn ngữ nghiệp vụ sang trách nhiệm và hợp đồng phần mềm.

## 2. Chọn đúng phạm vi và người cung cấp thông tin

Trước khi phỏng vấn, xác định **ranh giới hệ thống** (system boundary), mục tiêu và các bên liên quan.

| Thành phần | Câu hỏi cần làm rõ | Ví dụ trong hệ thống đăng ký học |
|---|---|---|
| Actor chính | Ai khởi động tương tác để đạt mục tiêu? | Sinh viên |
| Bên liên quan khác | Ai đặt/duyệt quy tắc, ai chịu hậu quả? | Phòng đào tạo, giảng viên, quản trị viên |
| Mục tiêu | Kết quả có giá trị với actor là gì? | Có một suất học hợp lệ |
| Hệ thống ngoài | Phụ thuộc vào hệ thống nào? | Đăng nhập, quản lý học vụ, email |
| Phạm vi | Phần nào do ứng dụng này chịu trách nhiệm? | Kiểm tra điều kiện và ghi danh |
| Điều chưa chắc chắn | Ai được quyền quyết định câu trả lời? | Phòng đào tạo xác nhận chính sách đủ điều kiện |
| Ràng buộc phi chức năng | Khối lượng, thời gian phản hồi, an toàn, audit? | Nhiều lượt đăng ký cùng lúc, không vượt sức chứa |

Một yêu cầu “kiểm tra sinh viên đã học môn A” có thể lấy dữ liệu từ hệ thống đào tạo khác. Khi đó cần biết hệ thống nào là **nguồn sự thật** (*source of truth*), thời điểm dữ liệu được cập nhật và cách ứng dụng xử lý khi dịch vụ đó không sẵn sàng.

## 3. Thu thập yêu cầu bằng tình huống cụ thể

Các kỹ thuật thực tế nên kết hợp thay vì chỉ hỏi “cần những màn hình nào?”.

### Phỏng vấn theo mục tiêu

Hỏi sinh viên về thao tác, hỏi phòng đào tạo về chính sách, hỏi vận hành về ngoại lệ và sai lệch dữ liệu. Ví dụ:

1. “Lần gần nhất bạn đăng ký môn học diễn ra như thế nào, từ đầu tới cuối?”
2. “Có tình huống nào hệ thống từ chối nhưng cán bộ vẫn chấp nhận ngoại lệ?”
3. “Thế nào được tính là **một** suất trong khóa học: mỗi tài khoản, mỗi sinh viên, mỗi lần ghi danh?”
4. “Khi hai người đăng ký chỗ cuối cùng cùng lúc, hệ thống phải quyết định thế nào?”
5. “Chúng ta kiểm chứng đăng ký thành công bằng dữ liệu hoặc sự kiện nào?”
6. “Ai có thể điều chỉnh chính sách, và có cần giữ lịch sử phiên bản không?”

Tránh câu hỏi gợi ý “Mình nên có nút Đăng ký chứ?” vì dễ chuyển cuộc thảo luận sang UI trước khi hiểu mục tiêu.

### Quan sát và đi theo quy trình (observation / shadowing)

Xem nhân viên nghiệp vụ xử lý hồ sơ thật, đầu vào, quyết định và các thao tác ngoại lệ. Một câu “đăng ký hợp lệ” có thể che giấu kiểm tra tín chỉ, lịch trùng, môn tiên quyết và khoản nợ học phí. Đừng thêm các quy tắc này vào mô hình nếu bên nghiệp vụ chưa xác nhận.

### Workshop ví dụ và phản ví dụ

Dùng ví dụ có số liệu để tránh từ mơ hồ:

| Tình huống được đưa ra | Câu hỏi cần chốt |
|---|---|
| Còn 1 chỗ, có 2 lượt đăng ký đồng thời | Ai thắng? Có hàng đợi không? |
| Sinh viên học xong môn tiên quyết nhưng bảng điểm chưa đồng bộ | Từ chối, chờ đồng bộ hay cho đăng ký có điều kiện? |
| Đã ghi danh và gửi yêu cầu giống hệt lần nữa | Báo “đã đăng ký”, trả kết quả cũ hay tạo lỗi? |
| Đăng ký thành công, email thất bại | Có hủy đăng ký không? Có retry không? |
| Khóa học đầy, quản trị viên tăng sức chứa | Ai được phép làm và có audit không? |

Mỗi ví dụ nên có **đầu vào, trạng thái trước, hành động, kết quả mong đợi, lý do**. Nếu stakeholder trả lời khác nhau, ghi lại xung đột cùng người quyết định, không tự chọn một đáp án.

### Event storming nhẹ

Viết các sự kiện đã xảy ra như “Sinh viên yêu cầu ghi danh”, “Đăng ký bị từ chối”, “Sinh viên đã ghi danh” rồi lần ngược lại:

- Điều gì kích hoạt sự kiện?
- Ai/đối tượng nào quyết định?
- Điều kiện nào phải đúng trước khi sự kiện xảy ra?
- Có cần lưu sự kiện, hay chỉ cần trạng thái cuối?
- Có hệ thống nào phản ứng sau sự kiện không?

Event storming giúp tìm ranh giới trách nhiệm, nhưng **không bắt buộc** triển khai event sourcing hay message broker.

## 4. Chuẩn hóa một tình huống sử dụng (Use Case Specification)

Ví dụ use case **UC-01 – Đăng ký khóa học**, trong phạm vi hệ thống giả định:

| Thuộc tính | Nội dung |
|---|---|
| **ID / Tên** | UC-01 / Đăng ký khóa học |
| **Mục tiêu** | Sinh viên có một lượt ghi danh hợp lệ vào khóa học |
| **Actor chính** | Sinh viên đã xác thực |
| **Kích hoạt** | Sinh viên yêu cầu đăng ký một khóa học được chọn |
| **Tiền điều kiện** | Hệ thống đã xác định danh tính sinh viên và khóa học; người dùng có quyền gửi yêu cầu |
| **Luồng thành công** | 1. Nhận yêu cầu → 2. Tải trạng thái sinh viên và khóa học → 3. Kiểm tra chính sách → 4. Ghi danh nguyên tử → 5. Trả xác nhận |
| **Luồng thay thế** | Tài khoản chưa kích hoạt, lớp đóng, thiếu môn tiên quyết, đăng ký trùng, hết chỗ |
| **Hậu điều kiện thành công** | Có đúng một ghi danh cho cặp sinh viên–khóa học; số chỗ trống giảm theo chính sách |
| **Bảo đảm khi thất bại** | Không tạo ghi danh mới hoặc vượt quá sức chứa |
| **Đầu ra** | Mã khóa học, mã sinh viên, trạng thái và thông điệp phù hợp |
| **Ngoài phạm vi ví dụ** | Thanh toán, hủy ghi danh, danh sách chờ, đăng ký thủ công của nhân viên |

Tiền điều kiện “đã xác thực” khác quy tắc “tài khoản đang **hoạt động**”: người dùng có thể đăng nhập được nhưng đang bị khóa ghi danh theo chính sách. Một use case specification tốt phân biệt các điều kiện đó.

Đừng chèn chi tiết như “click nút màu xanh ở góc phải” vào **use case nghiệp vụ**. Đó là UI design hoặc test giao diện; use case cần đủ trừu tượng để API, web hay mobile đều thực hiện cùng mục tiêu.

## 5. Ghi business rule sao cho kiểm tra được

Các quy tắc sau là **giả định được chọn để xây dựng ví dụ**:

| ID | Quy tắc nghiệp vụ | Kết quả khi vi phạm |
|---|---|---|
| BR-01 | Chỉ sinh viên có trạng thái **active** được ghi danh | Từ chối, không ghi danh |
| BR-02 | Chỉ nhận đăng ký khi khóa còn **mở** | Từ chối |
| BR-03 | Sinh viên đã hoàn thành **tất cả môn tiên quyết** của khóa | Từ chối |
| BR-04 | Một sinh viên có **tối đa một** ghi danh trong cùng một khóa | Từ chối yêu cầu trùng |
| BR-05 | Số ghi danh không được vượt **capacity** của khóa | Từ chối khi hết chỗ |
| BR-06 | Ghi danh thành công cập nhật trạng thái **một cách nguyên tử** | Không có trạng thái ghi một nửa |

Quy tắc tốt cần có:

- **ID ổn định** để tham chiếu trong use case, ticket, test và tài liệu.
- **Mệnh đề rõ ràng**: dữ liệu đầu vào, điều kiện và hành vi khi điều kiện không thỏa.
- **Người sở hữu quy tắc**: bộ phận nghiệp vụ có thẩm quyền quyết định.
- **Phạm vi áp dụng**: loại khóa học, chương trình học, khu vực, thời gian và ngoại lệ.
- **Hiệu lực và phiên bản** nếu chính sách có thể thay đổi theo học kỳ.
- **Ví dụ đúng/sai** để loại bỏ mơ hồ.

Ví dụ cụm “được đăng ký đủ điều kiện” không thể kiểm thử. Thay bằng “BR-03: trước khi ghi danh, tập môn đã hoàn thành phải chứa toàn bộ tập môn tiên quyết của khóa học”.

Phân biệt **business rule** và **technical constraint**:

- “Không vượt quá 30 sinh viên trong lớp có capacity = 30” là luật nghiệp vụ.
- “Cột `student_id` có type VARCHAR(36)” là lựa chọn kỹ thuật.
- “Mỗi sinh viên chỉ có một lượt ghi danh cho một khóa” là business rule; unique constraint `(course_id, student_id)` trong DB là **một cơ chế** để thực thi luật đó.

## 6. Các luồng ngoại lệ phải được đặc tả ngang với luồng thành công

Đừng dừng ở “thành công thì lưu vào DB”. Lập ma trận nghiệp vụ:

| Trạng thái trước khi gọi | Hành động | Kết quả mong đợi | Quy tắc |
|---|---|---|---|
| Sinh viên active, khóa mở, đủ tiên quyết, còn chỗ | Ghi danh | Thành công, số chỗ giảm 1 | BR-01..06 |
| Sinh viên không active | Ghi danh | Từ chối, không thay đổi số ghi danh | BR-01 |
| Khóa đóng | Ghi danh | Từ chối, trạng thái không đổi | BR-02 |
| Thiếu môn tiên quyết | Ghi danh | Từ chối, không giữ chỗ | BR-03 |
| Đã ghi danh khóa đó | Ghi danh lại | Từ chối hoặc trả kết quả cũ theo chính sách được chọn | BR-04 |
| Khóa đủ sức chứa | Ghi danh | Từ chối, không vượt capacity | BR-05 |
| Hai lượt giữ chỗ cuối cùng cùng lúc | Ghi danh | Tối đa một lượt thành công | BR-05, BR-06 |

Các phản ví dụ này trực tiếp trở thành acceptance criteria và test. Với yêu cầu gửi lại do mạng, hãy **chốt chính sách idempotency**: “yêu cầu trùng” và “retry cùng một yêu cầu” có thể cần hành vi khác nhau. Ví dụ Java đơn giản bên dưới chọn **từ chối đăng ký trùng**, chưa làm idempotency key.

## 7. Chuyển từ use case và business rule sang mô hình lớp

Đầu tiên tách **khái niệm**, **trạng thái**, **invariant** và **hành vi**:

| Khái niệm | Trạng thái tối thiểu | Hành vi / trách nhiệm |
|---|---|---|
| `Student` | ID, active, các môn đã hoàn thành | Cung cấp thông tin đủ điều kiện, giữ trạng thái sinh viên nhất quán |
| `Course` | ID, capacity, trạng thái mở, môn tiên quyết, tập sinh viên ghi danh | Quyết định có chấp nhận một lượt ghi danh; bảo vệ capacity/trùng |
| `EnrollmentReceipt` | Mã khóa, mã sinh viên, số ghi danh sau thao tác | Trả kết quả bất biến cho caller |
| `EnrollmentUseCase` (khi có DB/API thật) | Các dependency cần thiết | Tải dữ liệu, kiểm tra quyền, gọi domain, lưu transaction, trả kết quả |
| Repository / Adapter | Công nghệ lưu trữ | Lưu/tải domain state, đảm bảo transaction theo thiết kế |

Không phải danh từ nào cũng là class. “Nút đăng ký”, “màn hình”, “email” có thể thuộc presentation/integration, không nhất thiết là domain entity. Quy tắc “sức chứa” chưa cần lớp `CapacityValidator` riêng nếu nó chỉ là một invariant đơn giản, thuộc trách nhiệm của `Course`.

Có thể coi `Course` là **aggregate root** cho đăng ký chỗ trong ví dụ thu nhỏ, nếu tất cả lượt đăng ký được quản lý qua nó. Với hệ thống lớn, ghi danh có thể là aggregate riêng và việc bảo vệ capacity đặt ở reservation service/database; cách chia ranh giới phải dựa vào transaction, khối lượng truy cập và invariant thực tế.

~~~mermaid
classDiagram
    direction LR
    class Student {
        +id: String
        +active: boolean
        +completedCourses: Set
    }
    class Course {
        +id: String
        +capacity: int
        +enroll(Student) EnrollmentReceipt
        +remainingSeats() int
        +closeRegistration()
    }
    class EnrollmentReceipt {
        +courseId: String
        +studentId: String
        +enrolledCount: int
    }
    Course ..> Student : kiểm tra điều kiện
    Course ..> EnrollmentReceipt : tạo kết quả
~~~

Quan hệ phía trên là **phụ thuộc hành vi**, không đủ dữ liệu để kết luận composition hay aggregation. Nếu cần mô hình hóa vòng đời ghi danh như một entity riêng, có thể thêm `Enrollment` với identity và trạng thái; không nên thêm chỉ vì sơ đồ có nhiều danh từ.

## 8. Java 17+: hiện thực mẫu dựa trên quy tắc đã thu thập

Đây là một ví dụ **chạy được trong một tệp `EnrollmentModelingDemo.java`**. Dùng trạng thái trong bộ nhớ để làm rõ domain. Nó **không** thay thế transaction và unique constraint của database thật.

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

record Student(String id, boolean active, Set<String> completedCourses) {
    Student {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(completedCourses, "completedCourses");
        if (id.isBlank()) {
            throw new IllegalArgumentException("Student id is blank");
        }
        completedCourses = Set.copyOf(completedCourses);
    }
}

record EnrollmentReceipt(
        String courseId, String studentId, int enrolledCount) {}

final class BusinessRuleViolation extends RuntimeException {
    private final String ruleId;

    BusinessRuleViolation(String ruleId, String message) {
        super(message);
        this.ruleId = ruleId;
    }

    String ruleId() {
        return ruleId;
    }
}

final class Course {
    private final String id;
    private final int capacity;
    private final Set<String> prerequisites;
    private final Set<String> enrolledStudentIds = new LinkedHashSet<>();
    private boolean registrationOpen;

    Course(String id, int capacity, Set<String> prerequisites,
            boolean registrationOpen) {
        this.id = Objects.requireNonNull(id, "id");
        Objects.requireNonNull(prerequisites, "prerequisites");
        if (id.isBlank() || capacity <= 0) {
            throw new IllegalArgumentException("Invalid course");
        }
        this.capacity = capacity;
        this.prerequisites = Set.copyOf(prerequisites);
        this.registrationOpen = registrationOpen;
    }

    // Command: kiểm tra và thay đổi trong cùng vùng đồng bộ.
    synchronized EnrollmentReceipt enroll(Student student) {
        Objects.requireNonNull(student, "student");

        if (!student.active()) {
            throw new BusinessRuleViolation("BR-01", "Student is inactive");
        }
        if (!registrationOpen) {
            throw new BusinessRuleViolation("BR-02", "Registration is closed");
        }
        if (!student.completedCourses().containsAll(prerequisites)) {
            throw new BusinessRuleViolation("BR-03", "Prerequisites missing");
        }
        if (enrolledStudentIds.contains(student.id())) {
            throw new BusinessRuleViolation("BR-04", "Already enrolled");
        }
        if (enrolledStudentIds.size() >= capacity) {
            throw new BusinessRuleViolation("BR-05", "Course is full");
        }

        enrolledStudentIds.add(student.id()); // BR-06 trong 1 JVM
        return new EnrollmentReceipt(
                id, student.id(), enrolledStudentIds.size());
    }

    // Query: không thay đổi dữ liệu.
    synchronized int remainingSeats() {
        return capacity - enrolledStudentIds.size();
    }

    synchronized void closeRegistration() {
        registrationOpen = false;
    }
}

public class EnrollmentModelingDemo {
    public static void main(String[] args) {
        Course oop = new Course("OOP-201", 2, Set.of("JAVA-101"), true);
        Student lan = new Student("ST-01", true, Set.of("JAVA-101"));
        Student minh = new Student("ST-02", true, Set.of("JAVA-101"));

        EnrollmentReceipt result = oop.enroll(lan);
        System.out.println(result);
        System.out.println("Remaining: " + oop.remainingSeats()); // 1

        oop.enroll(minh);
        System.out.println("Remaining: " + oop.remainingSeats()); // 0

        try {
            oop.enroll(new Student(
                    "ST-03", true, Set.of("JAVA-101")));
        } catch (BusinessRuleViolation exception) {
            System.out.println(
                    exception.ruleId() + ": " + exception.getMessage());
            // BR-05: Course is full
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac EnrollmentModelingDemo.java
java EnrollmentModelingDemo
~~~

**Ý nghĩa thiết kế:**

- `Student` là `record` bất biến, `Set.copyOf` tránh caller thay đổi danh sách môn đã hoàn thành sau khi tạo.
- `Course.enroll()` bảo vệ các business rule thuộc trách nhiệm của khóa, thay vì đặt ở controller rồi hy vọng mọi caller đều kiểm tra.
- `BusinessRuleViolation.ruleId()` tạo **liên kết truy vết** giữa yêu cầu BR-xx, code và test; không nên trả stack trace nội bộ cho người dùng cuối.
- `synchronized` bảo đảm kiểm tra và thêm sinh viên không bị xen ngang khi **cùng một instance `Course` trong một JVM** được truy cập bởi nhiều luồng.
- `EnrollmentReceipt` chỉ chứa dữ liệu cần trả cho use case. Trong hệ thống thật có thể bổ sung enrollment ID, trạng thái, thời gian và version theo yêu cầu đã được xác nhận.

**Ranh giới quan trọng:** Nếu ứng dụng chạy trên nhiều node và mỗi node tải một `Course` riêng từ DB, các khóa `synchronized` **không** đồng bộ giữa các node. Để bảo vệ BR-04/BR-05/BR-06 trong hệ thống thực cần transaction đúng, unique constraint theo `(course_id, student_id)`, cơ chế khóa/optimistic version hoặc update có điều kiện và kiểm tra kết quả. Luật nghiệp vụ không tự được bảo đảm chỉ vì có `if` trong Java.

## 9. Truy vết yêu cầu → lớp → kiểm thử

Ma trận traceability giúp kiểm soát phạm vi và thấy luật nào thiếu kiểm chứng:

| Nguồn yêu cầu | Nơi thể hiện trong model | Ca kiểm thử |
|---|---|---|
| UC-01 luồng thành công | `Course.enroll()`, `EnrollmentReceipt` | Sinh viên hợp lệ được ghi danh, số chỗ giảm 1 |
| BR-01 | `Student.active()`, `Course.enroll()` | Sinh viên inactive bị từ chối |
| BR-02 | `Course.registrationOpen` | Khóa đóng bị từ chối |
| BR-03 | `Student.completedCourses`, `Course.prerequisites` | Thiếu môn bị từ chối |
| BR-04 | `Course.enrolledStudentIds` | Ghi danh lần hai bị từ chối |
| BR-05 | `Course.capacity` | Hết chỗ bị từ chối |
| BR-06 | `Course.enroll()` và persistence transaction khi dùng DB | Lỗi không thêm bản ghi, hai request tranh chỗ không vượt capacity |

Một tiêu chí nghiệp vụ có thể cần **nhiều** test; ngược lại một test có thể đi qua nhiều quy tắc. Traceability hữu ích khi chính sách thay đổi: tìm nhanh code và test phải sửa mà không buộc tất cả quy tắc thành một lớp lớn.

### Test JUnit Jupiter 5 minh họa

**`EnrollmentModelingTest.java`** (đặt cùng package với tệp demo):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Set;

class EnrollmentModelingTest {
    private static Student eligible(String id) {
        return new Student(id, true, Set.of("JAVA-101"));
    }

    @Test
    void successConsumesExactlyOneSeat() {
        Course course = new Course("OOP", 2, Set.of("JAVA-101"), true);

        EnrollmentReceipt receipt = course.enroll(eligible("S-01"));

        assertEquals("OOP", receipt.courseId());
        assertEquals("S-01", receipt.studentId());
        assertEquals(1, receipt.enrolledCount());
        assertEquals(1, course.remainingSeats());
    }

    @Test
    void duplicateDoesNotConsumeAnotherSeat() {
        Course course = new Course("OOP", 2, Set.of(), true);
        Student student = new Student("S-01", true, Set.of());
        course.enroll(student);

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class, () -> course.enroll(student));

        assertEquals("BR-04", exception.ruleId());
        assertEquals(1, course.remainingSeats());
    }

    @Test
    void missingPrerequisiteIsRejected() {
        Course course = new Course("OOP", 1, Set.of("JAVA-101"), true);

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class,
                () -> course.enroll(new Student("S-02", true, Set.of())));

        assertEquals("BR-03", exception.ruleId());
        assertEquals(1, course.remainingSeats());
    }

    @Test
    void capacityIsEnforced() {
        Course course = new Course("OOP", 1, Set.of(), true);
        course.enroll(new Student("S-01", true, Set.of()));

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class,
                () -> course.enroll(new Student("S-02", true, Set.of())));

        assertEquals("BR-05", exception.ruleId());
        assertEquals(0, course.remainingSeats());
    }

    @Test
    void closedRegistrationRejectsRequest() {
        Course course = new Course("OOP", 1, Set.of(), true);
        course.closeRegistration();

        BusinessRuleViolation exception = assertThrows(
                BusinessRuleViolation.class,
                () -> course.enroll(new Student("S-01", true, Set.of())));

        assertEquals("BR-02", exception.ruleId());
        assertEquals(1, course.remainingSeats());
    }
}
~~~

Các test trên kiểm tra hành vi đúng với quy tắc. Chúng chưa chứng minh uniqueness/atomicity đa node; cần integration test có DB và kiểm thử cạnh tranh phù hợp trước khi dùng cho hệ thống thật.

## 10. Acceptance criteria bằng Given–When–Then

Use case dài hữu ích cho bối cảnh, còn **Given–When–Then** biến từng tình huống thành tiêu chí có thể chấp nhận.

~~~gherkin
Feature: Đăng ký khóa học

  Scenario: Đăng ký hợp lệ
    Given sinh viên ST-01 đang hoạt động
      And ST-01 đã hoàn thành JAVA-101
      And khóa OOP-201 đang mở với 1 chỗ trống
    When ST-01 đăng ký OOP-201
    Then hệ thống xác nhận đăng ký thành công
      And OOP-201 có 0 chỗ trống

  Scenario: Từ chối đăng ký trùng
    Given ST-01 đã ghi danh OOP-201
    When ST-01 đăng ký lại OOP-201
    Then hệ thống từ chối theo BR-04
      And số chỗ trống không thay đổi
~~~

Đoạn Gherkin chỉ là **đặc tả tình huống**; để chạy tự động cần công cụ và step definitions thích hợp (ví dụ Cucumber). Nó không tự thực thi khi đặt vào file README.

Không biến mọi chi tiết UI thành tiêu chí acceptance. “Nút xanh xuất hiện” có thể cần test giao diện riêng; rule BR-04 phải được kiểm tra ở tầng nghiệp vụ ngay cả khi caller không dùng giao diện web.

## 11. Luồng nghiệp vụ, trạng thái và điểm quyết định

~~~mermaid
flowchart TD
    A[Sinh viên yêu cầu ghi danh] --> B[Định danh người yêu cầu và khóa học]
    B --> C{Sinh viên active?}
    C -->|Không| X1[Từ chối BR-01]
    C -->|Có| D{Khóa đang mở?}
    D -->|Không| X2[Từ chối BR-02]
    D -->|Có| E{Đủ môn tiên quyết?}
    E -->|Không| X3[Từ chối BR-03]
    E -->|Có| F{Đã ghi danh?}
    F -->|Có| X4[Từ chối BR-04]
    F -->|Không| G{Còn capacity?}
    G -->|Không| X5[Từ chối BR-05]
    G -->|Có| H[Giữ chỗ và tạo ghi danh nguyên tử]
    H --> I[Trả biên nhận]
~~~

Sơ đồ giúp stakeholder phát hiện nhánh chưa xác định. Thứ tự kiểm tra lỗi trong sơ đồ **chỉ là một lựa chọn của ví dụ**: trong hệ thống thật có thể ưu tiên kiểm tra quyền trước, hạn chế lộ thông tin khóa học hoặc xử lý trường hợp “đã đăng ký” khác. Thứ tự lỗi trả về là một phần hợp đồng cần xác nhận.

Nếu có vòng đời nhiều trạng thái (`Requested → Approved → Cancelled`, chẳng hạn), hãy vẽ **state machine** và ghi quy tắc chuyển trạng thái. Nhưng nếu use case chỉ có quyết định thành công/thất bại và chưa có trạng thái dài hạn bổ sung, không cần tự tạo hàng loạt state giả.

## 12. Quy tắc nghiệp vụ khác gì yêu cầu chức năng và phi chức năng?

| Nhóm | Ví dụ | Tác động lên mô hình |
|---|---|---|
| **Use case / functional requirement** | Sinh viên đăng ký khóa học | Cần thao tác điều phối và trả kết quả |
| **Business rule** | Không vượt sức chứa; không đăng ký trùng | Invariant và validation ở domain/transaction |
| **Non-functional requirement** | 99% yêu cầu trả lời trong ngưỡng do stakeholder quy định | Ảnh hưởng chiến lược truy cập DB, cache, phân tải |
| **Security rule** | Chỉ chủ tài khoản hoặc nhân viên được ủy quyền mới đăng ký thay | Authorization tại entry point và nơi thích hợp |
| **Data constraint** | Unique `(course_id, student_id)` | Bảo vệ tính nhất quán ở nơi lưu trữ |
| **UI behavior** | Hiển thị số chỗ còn lại, disabled khi đầy | Presentation; không thay thế kiểm tra của command |

Không viết một business rule mơ hồ thành ràng buộc cứng tại nhiều chỗ rồi quên quản lý phiên bản. Nếu cùng quy tắc được áp dụng ở API, DB và UI, xác định **nguồn định nghĩa chính** cùng chiến lược nhất quán giữa các lớp.

## 13. Quy trình thu thập và mô hình hóa có thể áp dụng ngay

1. **Xác định mục tiêu và system boundary.** Lập danh sách actor, hệ thống liên quan và kết quả mong đợi, tránh khởi đầu bằng danh sách class.
2. **Thu thập câu chuyện thực tế.** Phỏng vấn, quan sát workflow, dùng ví dụ có dữ liệu và phản ví dụ. Ghi rõ ai nói gì và điểm chưa được phê duyệt.
3. **Đặt tên use case theo động từ + kết quả.** Ví dụ “Đăng ký khóa học”, “Hủy ghi danh”, “Duyệt yêu cầu ngoại lệ”. Mỗi use case có actor và mục tiêu rõ.
4. **Đặc tả luồng chính và ngoại lệ.** Ghi trigger, preconditions, postconditions, bảo đảm khi lỗi và tình huống cạnh tranh.
5. **Chắt lọc business rule riêng.** Cấp mã BR-xx, diễn giải bằng điều kiện quan sát được, xác định owner, phạm vi, ngoại lệ và phiên bản.
6. **Xác nhận bằng ví dụ cụ thể.** Dùng bảng quyết định/Given–When–Then để stakeholder xác nhận cả dữ liệu sát biên, null/blank, trùng lặp và concurrency.
7. **Phác thảo domain model.** Xác định entity, value object, aggregate, invariants và trách nhiệm; chỉ thêm abstraction khi có nhu cầu thật.
8. **Thiết kế API/use case.** Command phải bảo vệ quy tắc tại nơi quản lý dữ liệu, query chỉ đọc; giao diện kỹ thuật không sở hữu tùy tiện policy nghiệp vụ.
9. **Tạo traceability.** Ánh xạ use case → business rule → class/method → test; duy trì cùng khi yêu cầu thay đổi.
10. **Review với stakeholder và người vận hành.** Kiểm tra tính thực thi, lỗi, audit, transaction, tích hợp và khả năng thay đổi theo thời gian.

~~~mermaid
flowchart LR
    A[Stakeholder và tình huống thực] --> B[Use case]
    B --> C[Business rules và acceptance criteria]
    C --> D[Domain model và trách nhiệm]
    D --> E[Java API / transaction / persistence]
    E --> F[Test truy vết]
    F -. phát hiện thiếu hoặc mâu thuẫn .-> B
~~~

Việc mô hình hóa là **lặp lại có kiểm soát**, không phải viết tài liệu một lần rồi bỏ. Nếu test khám phá một trường hợp nghiệp vụ chưa rõ, quay lại người sở hữu quy tắc để xác nhận thay vì chỉ thêm `if` theo phán đoán kỹ thuật.

## 14. Rủi ro thu thập yêu cầu và cách tránh

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chỉ ghi yêu cầu UI | Thiếu quy tắc domain, API khác dễ bỏ qua kiểm tra | Thu use case ở mức mục tiêu người dùng |
| Hỏi một stakeholder cho mọi quy tắc | Thiếu ngoại lệ và quyền quyết định | Xác định owner, người duyệt và các bên liên quan |
| Quy tắc dùng từ “hợp lệ”, “đủ”, “nhanh” | Không kiểm thử được | Thay bằng điều kiện, ngưỡng, ví dụ cụ thể |
| Lẫn policy với cách cài đặt | Lúc đổi DB/framework phải sửa tài liệu nghiệp vụ | Tách BR khỏi SQL, HTTP và class cụ thể |
| Chỉ mô tả happy path | Lỗi dữ liệu, thao tác cạnh tranh và retry không có định nghĩa | Tạo decision table và luồng thất bại |
| Biến mọi danh từ thành class | Nhiều lớp không có trách nhiệm rõ, coupling tăng | Xác định identity, state và invariants trước |
| Chỉ kiểm tra ở controller | Job/background caller bỏ qua rule | Đặt invariant ở domain/persistence phù hợp |
| Không gắn BR với test | Thay policy mà không biết vùng ảnh hưởng | Traceability BR-ID → behavior test |
| Xem in-memory lock là bảo đảm phân tán | Vượt capacity trên nhiều server | DB transaction/constraint/locking thích hợp |
| Không ghi giả định và phạm vi | Dev lặng lẽ quyết định chính sách thay stakeholder | Danh sách câu hỏi mở, quyết định, phiên bản |

## 15. Bài tập tự thực hành

**Bối cảnh khác:** hệ thống thư viện cho độc giả mượn sách.

Hãy thu thập và mô hình hóa use case **“Mượn một bản sách”** với yêu cầu ban đầu: “Độc giả được mượn sách còn sẵn”. Trước khi code, đề xuất ít nhất các câu hỏi về tài khoản hoạt động, số sách tối đa đang mượn, hạn mượn, bản sách cụ thể, việc đặt trước, trễ hạn, retry request và nhiều độc giả chọn cùng bản cuối.

Sau khi có câu trả lời, hãy:

1. Viết một use case UC-LIB-01 với actor, trigger, luồng thành công, các nhánh thất bại và hậu điều kiện.
2. Lập bảng BR-LIB-01... và ví dụ đúng/sai cho từng rule đã được xác nhận.
3. Xác định `BookTitle`, `BookCopy`, `Member`, `Loan` có danh tính và vòng đời thế nào; trách nhiệm giữ bản cuối nên đặt ở đâu.
4. Vẽ một sơ đồ use case flow và một class diagram vừa đủ; không tạo class chỉ từ danh từ.
5. Viết API Java cho command `borrowCopy(...)` và query `availableCopies(...)`; kiểm tra race condition ở hệ thống lưu trữ thật.
6. Chuyển ít nhất ba business rules thành acceptance tests và ánh xạ ID tương ứng.

**Tiêu chí hoàn thành:** Một stakeholder có thể đọc các tình huống và xác nhận hành vi; lập trình viên xác định được trách nhiệm của mỗi class; người kiểm thử lần theo được mỗi rule tới ca kiểm thử; và trường hợp lỗi không để dữ liệu ở trạng thái trái chính sách.

---

**Ghi nhớ:** Mô hình OOP tốt bắt đầu từ **người dùng muốn đạt kết quả gì** và **tổ chức cho phép kết quả đó trong điều kiện nào**. Use case cung cấp luồng mục tiêu; business rule cung cấp chính sách/invariant; Java class và test là cách hiện thực, bảo vệ và chứng minh hai loại yêu cầu đó.