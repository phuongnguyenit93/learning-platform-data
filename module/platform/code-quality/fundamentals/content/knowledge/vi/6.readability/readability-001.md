# Mã diễn đạt ý định và mô hình bài toán

Hãy tưởng tượng bạn nhận nhiệm vụ sửa chức năng đăng ký khóa học. Trong một phương thức dài có câu lệnh:

~~~java
if (s == 1 && n < max && !ids.contains(id)) {
    ids.add(id);
}
~~~

Đoạn mã ngắn và không khó đọc về mặt cú pháp Java. Nhưng để biết nó **đúng hay sai**, bạn phải tự hỏi: `s == 1` là trạng thái gì, `n` đang đếm gì, `max` là giới hạn nào, và vì sao không được có `id` trong danh sách? Nếu cần sửa quy tắc đăng ký, bạn còn phải tìm xem các điều kiện tương tự có xuất hiện ở nơi khác không.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Bài thuộc chương **Khả năng đọc** này tập trung vào một năng lực quan trọng: **mã nguồn phải giúp người đọc nhận ra ý định của người viết và các khái niệm của bài toán**, thay vì buộc họ lần theo chi tiết kỹ thuật để đoán quy tắc nghiệp vụ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **ý định nghiệp vụ** với **cách thực hiện bằng câu lệnh Java**.
- Đặt tên biến, hàm và kiểu dữ liệu theo những khái niệm có ý nghĩa trong bài toán.
- Đưa các quy tắc liên quan về đúng đối tượng hoặc thao tác để người đọc thấy được **bất biến** và **điều kiện hợp lệ**.
- Nhận ra khi nào cần một kiểu dữ liệu riêng, khi nào một phương thức đơn giản là đủ và khi nào việc trừu tượng hóa làm mã khó hiểu hơn.
- Đánh giá khả năng đọc qua các câu hỏi thực tế trong review, không chỉ qua độ ngắn hoặc số dòng mã.

## 1. Mã có thể dễ đọc cú pháp nhưng khó hiểu ý định

So sánh hai cách mô tả cùng một ý tưởng:

~~~java
// Cách A: người đọc phải giải mã điều kiện.
if (s == 1 && n < max && !ids.contains(id)) {
    ids.add(id);
}
~~~

~~~java
// Cách B: tên thao tác nói lên mục đích.
course.enroll(studentId);
~~~

Ở **cách A**, người đọc phải giải mã từng biến rồi tự tổng hợp quy tắc. Ở **cách B**, người đọc nhận ra hành động *đăng ký học viên vào khóa học*. Các điều kiện về trạng thái mở đăng ký, sức chứa và đăng ký trùng có thể được đóng gói phía sau thao tác `enroll`.

Điều này không có nghĩa cách B luôn đúng. Nếu `enroll` bỏ qua quy tắc, tên hay cũng không cứu được chương trình. **Tên gọi rõ ràng giúp truyền đạt ý định; thiết kế và kiểm thử phải bảo đảm phần triển khai thực hiện đúng ý định đó.**

Có thể phân biệt ba tầng thông tin:

| Tầng | Câu hỏi người đọc cần trả lời | Ví dụ |
| --- | --- | --- |
| **Ý định** | Đang muốn đạt điều gì? | Đăng ký một học viên vào khóa học |
| **Quy tắc bài toán** | Khi nào việc đó hợp lệ? | Khóa học còn mở, còn chỗ và học viên chưa đăng ký |
| **Cơ chế triển khai** | Java thực hiện bằng cấu trúc nào? | Kiểm tra `enum`, so sánh số lượng, tra cứu `Set` rồi thêm phần tử |

Mã dễ hiểu là mã cho phép người bảo trì đi từ **ý định → quy tắc → cơ chế** khi họ cần, thay vì bắt đầu với những thao tác máy tính rồi suy ngược ra mục tiêu nghiệp vụ.

## 2. Bắt đầu từ ngôn ngữ của bài toán

Giả sử yêu cầu nghiệp vụ của một hệ thống đào tạo như sau:

> Một khóa học có sức chứa cố định. Học viên được đăng ký nếu khóa học đang mở, còn chỗ và học viên đó chưa đăng ký. Khóa học đã đóng không nhận thêm học viên.

Trước khi viết mã, ta xác định những khái niệm quan trọng:

| Tên trong nghiệp vụ | Ý nghĩa được thống nhất | Biểu diễn Java khả dĩ |
| --- | --- | --- |
| Khóa học | Đơn vị nhận học viên và quản lý sức chứa | `Course` |
| Học viên | Người có định danh duy nhất trong phạm vi hệ thống | `StudentId` |
| Trạng thái đăng ký | Đang mở hoặc đã đóng | `CourseStatus.OPEN`, `CourseStatus.CLOSED` |
| Sức chứa | Số học viên tối đa được chấp nhận | `capacity` |
| Danh sách đã đăng ký | Tập định danh học viên đã được nhận | `Set<StudentId>` |
| Còn chỗ | Số lượng đăng ký nhỏ hơn sức chứa | `hasAvailableSeat()` |
| Đăng ký | Hành động thêm học viên nếu các điều kiện hợp lệ | `enroll(studentId)` |

Những tên này hình thành một **ngôn ngữ chung** giữa người làm sản phẩm, người viết mã và người kiểm thử. Khi yêu cầu thay đổi, mọi người có thể trao đổi về “khóa học đã đóng”, “đăng ký trùng” hoặc “sức chứa” mà không cần nói vòng qua `flag`, `list` và `count`.

Tên trong mã nên phản ánh **định nghĩa đã thống nhất**, không nhất thiết sao chép nguyên văn một thuật ngữ tiếng Anh. Chẳng hạn, nếu sản phẩm phân biệt *đăng ký* (`enrollment`) và *giữ chỗ tạm thời* (`reservation`), không nên dùng chung tên `register` cho cả hai hành vi. Một cái tên có ý nghĩa chỉ khi người trong dự án hiểu nó theo cùng một cách.

### Từ ngữ chung không có nghĩa tạo kiểu riêng cho mọi danh từ

Không cần lập lớp `Capacity` chỉ vì nghiệp vụ có từ “sức chứa”. Trong ví dụ đơn giản, `int capacity` với điều kiện lớn hơn 0 có thể đã đủ rõ. Ngược lại, nếu định danh học viên và định danh khóa học đều là `String` nhưng thường bị truyền nhầm cho nhau, hai kiểu `StudentId` và `CourseId` có thể giúp làm rõ ý định ngay tại chữ ký phương thức.

**Chọn biểu diễn nhỏ nhất vẫn làm rõ được ý nghĩa và các quy tắc quan trọng.**

## 3. Đưa quy tắc vào đúng nơi: ví dụ Java

Nếu mã kiểm tra điều kiện được rải ở giao diện, controller và service, mỗi nơi có thể dần diễn giải quy tắc khác nhau. Thay vì buộc mọi nơi tự ghép điều kiện, ta có thể đưa quyết định đăng ký vào đối tượng `Course`.

Ví dụ sau sử dụng **Java 17 trở lên** và giả định việc thao tác với đối tượng diễn ra trong một luồng; phần đồng thời và lưu trữ được bàn riêng ở cuối bài.

~~~java
public enum CourseStatus {
    OPEN,
    CLOSED
}
~~~

Sử dụng `enum` giúp người đọc thấy tập trạng thái được hỗ trợ, thay cho các số không có tên như `1` hoặc `2`.

~~~java
public record StudentId(String value) {
    public StudentId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Student ID must not be blank"
            );
        }
    }
}
~~~

`StudentId` là một **kiểu giá trị (value object)** nhỏ. Nó biểu thị rằng giá trị đang được dùng là định danh học viên và ngăn tạo định danh trống. Với Java `record`, các đối tượng `StudentId` có cùng `value` được xem là bằng nhau, nên phù hợp để lưu trong `Set`.

Phần quản lý đăng ký:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class Course {
    private final int capacity;
    private final Set<StudentId> enrolledStudents = new HashSet<>();
    private CourseStatus status;

    public Course(int capacity, CourseStatus initialStatus) {
        if (capacity <= 0) {
            throw new IllegalArgumentException(
                "Capacity must be positive"
            );
        }
        this.capacity = capacity;
        this.status = Objects.requireNonNull(initialStatus);
    }

    public boolean canEnroll(StudentId studentId) {
        Objects.requireNonNull(studentId, "studentId");
        return status == CourseStatus.OPEN
            && hasAvailableSeat()
            && !enrolledStudents.contains(studentId);
    }

    public void enroll(StudentId studentId) {
        if (!canEnroll(studentId)) {
            throw new IllegalStateException(
                "Enrollment is not allowed"
            );
        }
        enrolledStudents.add(studentId);
    }

    public int remainingSeats() {
        return capacity - enrolledStudents.size();
    }

    public int enrolledCount() {
        return enrolledStudents.size();
    }

    public void closeRegistration() {
        status = CourseStatus.CLOSED;
    }

    private boolean hasAvailableSeat() {
        return enrolledStudents.size() < capacity;
    }
}
~~~

Ở mức gọi, ý định được thể hiện ngắn gọn:

~~~java
Course course = new Course(2, CourseStatus.OPEN);
StudentId studentId = new StudentId("ST-001");

course.enroll(studentId);
~~~

Người đọc đoạn gọi không cần biết dữ liệu được giữ bằng `HashSet` hay cơ chế nào khác. Khi cần xem **vì sao việc đăng ký hợp lệ**, họ có thể mở phương thức `canEnroll` và đọc một câu gần với quy tắc nghiệp vụ.

### Những quyết định thiết kế cụ thể

1. **Dùng `CourseStatus`:** trạng thái có tên và tập giá trị xác định. Không cần nhớ `1` tương đương “đang mở”.
2. **Dùng `StudentId`:** cho thấy tham số là định danh học viên. Kiểu này cũng kiểm tra dữ liệu đầu vào quan trọng.
3. **Dùng `Set<StudentId>`:** tập hợp diễn đạt yêu cầu mỗi học viên chỉ xuất hiện một lần. Tuy nhiên, bản thân `Set` chưa đủ để phát sinh lỗi khi đăng ký trùng, vì thao tác `add` có thể chỉ trả `false`; phương thức `enroll` vẫn cần kiểm tra quy tắc.
4. **Đặt `hasAvailableSeat()` trong `Course`:** công thức đếm chỗ trống là chi tiết có thể được thay đổi ở một nơi.
5. **Dùng `enroll()` để bảo vệ điều kiện:** bên gọi yêu cầu “đăng ký” và đối tượng quyết định có được chấp nhận hay không. Việc bên gọi chỉ kiểm tra `canEnroll()` không đủ thay thế cho kiểm tra bên trong `enroll()`.
6. **Không trả ra tập nội bộ có thể sửa:** nếu cho phép bên ngoài tự thêm hoặc xóa phần tử trong `enrolledStudents`, bên ngoài có thể vượt qua quy tắc đăng ký.

Ví dụ này chỉ minh họa cách mã diễn đạt ý định. Trong sản phẩm thực tế, cần thêm các quy tắc được xác nhận, chẳng hạn quyền đăng ký, học viên đã đóng học phí hay chưa, hoặc cách xử lý danh sách chờ. Không nên tự thêm chúng nếu yêu cầu chưa quy định.

## 4. Đặt tên để giảm suy luận

Tên tốt giúp người đọc trả lời **“dữ liệu này có nghĩa gì?”** và **“hành động này làm gì?”** ngay khi nhìn vào mã.

| Tên khó hiểu | Tên rõ nghĩa hơn | Lý do |
| --- | --- | --- |
| `s` | `registrationStatus` | Cho biết đây là trạng thái của việc đăng ký |
| `max` | `capacity` | Nói rõ giới hạn sức chứa khóa học |
| `list` | `enrolledStudents` | Cho biết tập dữ liệu chứa những ai |
| `check()` | `canEnroll(studentId)` | Biểu diễn câu hỏi đúng/sai cụ thể |
| `handle()` | `enroll(studentId)` | Biểu diễn hành động nghiệp vụ |
| `getN()` | `remainingSeats()` | Trả về một khái niệm có đơn vị ngầm rõ ràng |
| `doProcess()` | `closeRegistration()` | Tên nói rõ thay đổi trạng thái |

Tên không nên quá dài chỉ để kể lại mọi chi tiết. `isCourseCurrentlyOpenForReceivingOneMoreStudentRegistration` dài hơn `canEnroll` nhưng chưa chắc hữu ích hơn. Nếu hành động và đối tượng đã tạo đủ ngữ cảnh, một tên ngắn và chính xác sẽ dễ đọc hơn.

### Phân biệt tên trả lời câu hỏi và tên ra lệnh

Nên tách rõ:

- **Câu hỏi:** `canEnroll(studentId)` trả về `boolean`, không thay đổi danh sách đăng ký.
- **Mệnh lệnh:** `enroll(studentId)` thực hiện đăng ký hoặc báo lỗi theo hợp đồng.
- **Truy vấn dữ liệu:** `remainingSeats()` trả về số chỗ còn lại.

Khi phương thức có tên `isEligible()` nhưng đồng thời tự thêm học viên vào danh sách, người đọc dễ hiểu sai vì một **câu hỏi** lại phát sinh tác dụng phụ. Giữ vai trò của tên phương thức nhất quán giúp tránh sử dụng nhầm.

## 5. Mô hình bài toán phải chứa cả quy tắc, không chỉ chứa dữ liệu

Một cách tổ chức thường gặp là đối tượng `Course` chỉ có các trường dữ liệu và getter/setter. Mọi đoạn mã bên ngoài tự thực hiện:

~~~java
// Bên ngoài tự ghép và tự duy trì quy tắc.
if (course.getStatus() == CourseStatus.OPEN
        && course.getEnrolledCount() < course.getCapacity()
        && !course.getStudentIds().contains(studentId)) {
    course.getStudentIds().add(studentId);
}
~~~

Đoạn mã này có ba vấn đề về khả năng đọc và thay đổi:

1. Quy tắc “được đăng ký khi nào” bị giấu trong một biểu thức dài ở nơi gọi.
2. Các nơi khác có thể sao chép biểu thức và vô tình bỏ sót điều kiện.
3. Việc cấp quyền sửa trực tiếp tập học viên khiến đối tượng `Course` không thể tự bảo vệ điều kiện “không trùng” hoặc “không vượt sức chứa”.

Mô hình tốt không nhất thiết phải có nhiều lớp. Điểm chính là **quy tắc thuộc trách nhiệm nào thì nên được diễn đạt và bảo vệ ở trách nhiệm đó**. Khi quy tắc đăng ký thay đổi, người bảo trì có thể tìm đến `Course.enroll()` thay vì dò nhiều controller, handler hoặc service.

### Bất biến nói gì về ý định của mô hình?

**Bất biến (invariant)** là điều kiện cần luôn đúng trong phạm vi đã xác định. Với mô hình ví dụ:

- Sức chứa `capacity` là số nguyên dương.
- Số học viên đã đăng ký không vượt quá sức chứa.
- Mỗi `StudentId` chỉ xuất hiện một lần trong tập đã đăng ký.
- Một thao tác đăng ký thành công chỉ được thực hiện khi khóa học đang mở.

Nếu mô hình có phương thức `setCapacity(-5)` hay cho bên ngoài lấy `Set` và tự thêm học viên, người đọc khó tin rằng các bất biến trên thực sự được bảo vệ. **Thiết kế kiểu và API** nên làm cho trạng thái sai khó hình thành, hoặc ít nhất khiến đường dẫn gây lỗi trở nên rõ ràng và có thể kiểm soát.

Tuy nhiên, việc đóng gói không tự bảo đảm mọi tình huống vận hành. Nếu nhiều yêu cầu đăng ký một lúc, hai luồng có thể cùng thấy `hasAvailableSeat() == true` và vượt sức chứa. Đối tượng `Course` minh họa ở trên **không an toàn cho truy cập đồng thời**. Hệ thống thực tế có thể cần khóa, kiểm soát phiên bản lạc quan, transaction và ràng buộc cơ sở dữ liệu phù hợp với kiến trúc lưu trữ. Điều quan trọng là quy tắc nghiệp vụ vẫn được phát biểu rõ và được bảo vệ tại những ranh giới cần thiết.

## 6. Ý định của mã không dừng ở tên lớp

Người đọc còn cần hiểu **dòng chảy công việc**. So sánh:

~~~java
// Khó hiểu: các bước kỹ thuật che khuất lý do thực hiện.
var data = repository.findById(id);
if (data != null && data.getStatus() == 1) {
    data.setStatus(2);
    repository.save(data);
    eventClient.send(id);
}
~~~

với luồng được mô tả bằng những khái niệm có ý nghĩa:

~~~java
// Phác thảo cách tổ chức ý định, không phải cài đặt hoàn chỉnh.
Order order = orderRepository.requireById(orderId);
order.confirm();
orderRepository.save(order);
orderEvents.publishConfirmed(order.id());
~~~

Ở ví dụ thứ hai, người đọc có thể nhận ra: **lấy đơn hàng → xác nhận → lưu → thông báo**. Nhưng việc xác nhận và phát sự kiện đúng đắn trong thực tế còn phụ thuộc quy tắc giao dịch, xử lý lỗi và phát lại; chỉ đổi tên phương thức không làm những vấn đề ấy biến mất.

Một cách tổ chức có ích là để các lớp điều phối trình bày **trình tự công việc**, còn đối tượng hoặc thành phần nghiệp vụ thể hiện **quy tắc quyết định**. Các chi tiết như JDBC, HTTP, JSON hoặc cơ chế lưu trữ nên được đặt ở nơi chuyên trách khi chúng cản trở người đọc hiểu ý định chính.

Không cần che giấu mọi chi tiết kỹ thuật. Nếu đang đọc một lớp chuyên trách truy vấn database, các tên như `executeQuery`, `batchSize`, `transaction` lại chính là ngôn ngữ đúng của lớp đó. **Tên phù hợp tùy theo mức trừu tượng và trách nhiệm của đoạn mã.**

## 7. Khi nào nên tạo phương thức, kiểu hoặc lớp mới?

Việc tách mã nên được dẫn dắt bởi **khái niệm có ý nghĩa và trách nhiệm rõ ràng**, thay vì áp đặt một độ dài phương thức cố định.

| Tình huống | Có thể làm gì? | Vì sao? |
| --- | --- | --- |
| Một điều kiện có ý nghĩa nghiệp vụ và xuất hiện nhiều nơi | Tạo phương thức `canEnroll()` | Quy tắc có tên, dễ tìm và thay đổi |
| Hai loại định danh `String` dễ bị truyền nhầm | Tạo `StudentId`, `CourseId` | Kiểu giúp phân biệt ý nghĩa |
| Một tổ hợp số/trường có quy tắc luôn phải đúng | Cân nhắc value object | Tập trung việc kiểm tra bất biến |
| Một phương thức chứa nhiều bước thuộc các trách nhiệm khác nhau | Tách các bước theo tên mô tả mục đích | Luồng chính rõ ràng hơn |
| Một biểu thức chỉ dùng một lần và đã đủ rõ | Giữ nguyên | Tránh phải chuyển qua nhiều hàm vô ích |
| Chưa có nhiều cách xử lý thực tế | Chưa cần interface hoặc strategy phức tạp | Giảm lớp trung gian và chi phí đọc |

**Ví dụ trừu tượng hóa quá mức:** nếu hệ thống chỉ có một quy tắc “khóa học mở và còn chỗ thì được đăng ký”, việc tạo `EnrollmentEligibilityStrategyFactory`, `EligibilityRuleRegistry` và hàng loạt lớp cấu hình có thể làm người đọc khó tìm ra điều kiện thật sự.

Ngược lại, nếu chính sách khác nhau theo loại khóa học, kỳ tuyển sinh và quy định của nhiều tổ chức, một đối tượng chính sách riêng có thể cần thiết. Quyết định phải dựa vào **sự biến thiên có thật trong bài toán** và mức độ khó hiểu mà cách tổ chức hiện tại gây ra.

## 8. Bình luận, tài liệu và ví dụ phải bổ sung ý định

Bình luận lặp lại chính câu lệnh thường ít giá trị:

~~~java
// Kiểm tra xem còn chỗ không.
if (enrolledStudents.size() < capacity) {
    // Thêm học viên.
    enrolledStudents.add(studentId);
}
~~~

Những bình luận này không giải thích **vì sao** điều kiện tồn tại hoặc quy tắc được quyết định như vậy.

Một bình luận hữu ích hơn có thể ghi rõ **lý do không hiển nhiên**:

~~~java
// Chính sách kỳ tuyển sinh này chỉ chấp nhận các chỗ còn trống thực sự;
// chỗ đang giữ tạm không được tính là chỗ có thể đăng ký.
int seatsAvailableForEnrollment = capacity
    - confirmedEnrollments
    - reservedSeats;
~~~

Ở đây, cả tên biến và bình luận cùng truyền đạt quy tắc. Bình luận phải khớp với quyết định nghiệp vụ mới nhất; một bình luận cũ sai có thể nguy hiểm hơn việc không có bình luận.

Nên ưu tiên:

- **Tên** để diễn đạt điều dữ liệu hoặc thao tác đại diện.
- **Cấu trúc mã** để biểu diễn trách nhiệm và quan hệ giữa các bước.
- **Kiểm thử và ví dụ** để minh họa các trường hợp được phép, bị từ chối và tình huống biên.
- **Bình luận** để giải thích lý do, ràng buộc đặc biệt hoặc đánh đổi không thể thể hiện gọn bằng mã.

## 9. Kiểm thử cũng là tài liệu về mô hình

Kiểm thử với tên và dữ liệu rõ nghĩa có thể giúp người mới hiểu quy tắc đăng ký:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class CourseTest {
    @Test
    void acceptsStudentWhenRegistrationIsOpenAndSeatIsAvailable() {
        Course course = new Course(1, CourseStatus.OPEN);
        StudentId student = new StudentId("ST-001");

        assertTrue(course.canEnroll(student));
        course.enroll(student);

        assertEquals(1, course.enrolledCount());
        assertEquals(0, course.remainingSeats());
        assertFalse(course.canEnroll(student));
    }

    @Test
    void rejectsDuplicateEnrollment() {
        Course course = new Course(2, CourseStatus.OPEN);
        StudentId student = new StudentId("ST-001");
        course.enroll(student);

        assertThrows(IllegalStateException.class,
            () -> course.enroll(student));
        assertEquals(1, course.enrolledCount());
    }

    @Test
    void rejectsEnrollmentWhenCourseIsFull() {
        Course course = new Course(1, CourseStatus.OPEN);
        course.enroll(new StudentId("ST-001"));

        assertThrows(IllegalStateException.class,
            () -> course.enroll(new StudentId("ST-002")));
    }

    @Test
    void rejectsEnrollmentAfterRegistrationCloses() {
        Course course = new Course(2, CourseStatus.OPEN);
        course.closeRegistration();

        assertThrows(IllegalStateException.class,
            () -> course.enroll(new StudentId("ST-001")));
    }
}
~~~

Tên test thể hiện **điều kiện và kết quả**, không chỉ tên phương thức được gọi. Người đọc nhìn vào `rejectsDuplicateEnrollment` biết ngay một quy tắc có thể kiểm tra. Dù vậy, test chỉ chứng minh các trường hợp đã thực thi; nó không thay thế cho việc xác nhận quy tắc với người phụ trách nghiệp vụ.

## 10. Cách đánh giá mã có thực sự diễn đạt ý định

Trong code review, thay vì chỉ hỏi “đã đúng format chưa?”, hãy tự kiểm tra:

1. **Sau khi đọc tên lớp và phương thức, tôi có đoán được trách nhiệm và kết quả mong muốn không?** Nếu không, hãy tìm thuật ngữ nghiệp vụ phù hợp hơn.
2. **Điều kiện quan trọng có tên rõ nghĩa không?** Những biểu thức dài hoặc chứa `magic number` có thể đang che giấu quy tắc.
3. **Thông tin nào phải đọc từ nơi khác mới hiểu được?** Nhiều bước nhảy giữa các helper nhỏ cũng có thể khiến ý định bị phân mảnh.
4. **Một quy tắc có bị lặp ở nhiều chỗ không?** Nếu có, thay đổi yêu cầu có thể khiến các nơi xử lý lệch nhau.
5. **Kiểu dữ liệu có thể hiện ý nghĩa và đơn vị không?** `amountVnd` rõ hơn `amount` khi cùng hệ thống có nhiều đồng tiền; `StudentId` rõ hơn một `String` dễ nhầm.
6. **Trạng thái không hợp lệ có thể được tạo ra quá dễ dàng không?** Hãy xem constructor, setter và các collection nội bộ có bảo vệ bất biến không.
7. **Tên và bình luận có đúng với hành vi hiện tại không?** Tên tốt nhưng sai thực tế vẫn gây hiểu lầm.
8. **Mức độ trừu tượng có hợp lý không?** Người đọc có thể hiểu luồng chính mà không phải đi qua nhiều lớp vô nghĩa, và khi cần vẫn tìm được cơ chế thực hiện.

Khả năng đọc luôn có yếu tố bối cảnh: một người mới học Java và một người hiểu hệ thống lâu năm có thể đọc cùng đoạn mã với mức nỗ lực khác nhau. Dù vậy, cách đặt tên nhất quán theo khái niệm nghiệp vụ, các phương thức có trách nhiệm rõ ràng và kiểm thử có ý nghĩa thường giúp **giảm lượng kiến thức ngầm** mà người bảo trì phải tự đoán.

## 11. Bài tập thực hành

Bạn được giao review đoạn mã mô phỏng:

~~~java
void add(String x) {
    if (mode == 1 && list.size() < limit && !list.contains(x)) {
        list.add(x);
    }
}
~~~

Giả sử nhóm nghiệp vụ xác nhận: `mode == 1` nghĩa là khóa học đang mở đăng ký; `list` chứa định danh học viên đã ghi danh; `limit` là sức chứa; học viên không được ghi danh hai lần.

**Câu hỏi A.** Hãy đề xuất tên mới cho phương thức, tham số và các biến quan trọng để diễn đạt đúng ý định.

**Câu hỏi B.** Hành vi nào của đoạn mã hiện tại chưa được mô tả rõ và cần hỏi lại người phụ trách nghiệp vụ?

**Câu hỏi C.** Nếu nhiều yêu cầu đăng ký có thể chạy đồng thời, cần lưu ý điều gì trước khi khẳng định chương trình giữ đúng sức chứa?

### Gợi ý đáp án

**A.** Có thể dùng `enroll(StudentId studentId)`, `registrationStatus`, `enrolledStudents`, `capacity`. Đặt hành vi kiểm tra vào `Course.canEnroll(studentId)` và gọi từ `Course.enroll(studentId)`.

**B.** Cần làm rõ: khi khóa học đầy hoặc đã đóng thì trả kết quả gì, đăng ký trùng có báo lỗi hay bỏ qua, xử lý định danh trống hoặc không hợp lệ thế nào, có chính sách danh sách chờ hay không, ai có quyền mở/đóng đăng ký. Không nên tự đặt các quy tắc mới rồi coi đó là yêu cầu đã có.

**C.** Phép kiểm tra `list.size() < limit` rồi thêm phần tử là thao tác gồm nhiều bước, có thể không an toàn khi hai yêu cầu chạy cùng lúc. Cần thiết kế bảo vệ tính nhất quán ở mức phù hợp, chẳng hạn transaction, khóa hoặc kiểm soát phiên bản, và kiểm thử tình huống cạnh tranh.

## Ghi nhớ

Mã nguồn diễn đạt tốt ý định khi người đọc nhìn thấy **những khái niệm, hành động và quy tắc của bài toán** ngay trong tên gọi, kiểu dữ liệu và cấu trúc phương thức. Mục đích là giảm suy luận, giúp dễ kiểm tra tính đúng đắn và dễ thay đổi khi yêu cầu phát triển.

Một mô hình dễ đọc cần đặt **trách nhiệm đúng chỗ**, bảo vệ **bất biến quan trọng**, sử dụng **ngôn ngữ thống nhất với nghiệp vụ**, và chọn mức trừu tượng vừa đủ. Những tên gọi đẹp chỉ có giá trị khi hành vi thực tế và các phép kiểm tra cùng phản ánh đúng mô hình đó.
