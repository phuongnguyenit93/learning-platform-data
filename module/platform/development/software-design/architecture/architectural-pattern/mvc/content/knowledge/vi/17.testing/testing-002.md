# Kiểm thử quy tắc nghiệp vụ của Model

Trong MVC, Model biểu diễn trạng thái và hành vi của miền nghiệp vụ. Model có thể từ chối một thao tác, thay đổi trạng thái hoặc bảo vệ một bất biến dựa trên dữ liệu hiện tại. Những quyết định này cần được kiểm thử trực tiếp để bảo đảm ứng dụng luôn tuân theo quy tắc, bất kể hành động đến từ biểu mẫu HTML, REST API, tác vụ nền hay message consumer.

Ví dụ, một công việc chỉ được hoàn thành khi đang ở trạng thái thực hiện; một đơn hàng đã giao không thể bị hủy; số lượng đặt mua phải lớn hơn 0; người được giao việc phải là thành viên của dự án. Đây là quy tắc của Model hoặc chính sách nghiệp vụ, không phải chi tiết của Controller hay View. Kiểm thử Model nên tập trung vào hành vi có thể quan sát qua hợp đồng công khai: đầu vào nào được chấp nhận, trạng thái nào được tạo ra và điều kiện nào khiến thao tác bị từ chối.

Kiểm thử quy tắc Model thường là unit test nhanh, độc lập với Spring MVC, HTTP và cơ sở dữ liệu. Những vấn đề phụ thuộc persistence, transaction hoặc nhiều request đồng thời cần kiểm thử tích hợp ở ranh giới tương ứng. Phân biệt đúng các mức kiểm thử giúp phát hiện lỗi ở nơi quy tắc thực sự được bảo vệ.

## Xác định Model cần kiểm thử

Trong ngữ cảnh MVC, từ “Model” có thể chỉ nhiều thứ khác nhau. Bài học này tập trung vào **Domain Model**: entity, aggregate, value object, domain service và policy chứa quy tắc nghiệp vụ.

Không nhầm Domain Model với `org.springframework.ui.Model` trong Spring MVC. Đối tượng `Model` của Spring là vùng chứa dữ liệu gửi đến View trong một lần xử lý request; nó không phải đối tượng bảo vệ trạng thái và bất biến của miền.

Các đối tượng miền thường cần kiểm thử gồm:

- **Entity:** có định danh và trạng thái thay đổi theo hành vi, ví dụ `Task`, `Order`, `Account`.
- **Aggregate root:** kiểm soát các thay đổi bên trong một ranh giới nhất quán, ví dụ `Order` quản lý các dòng hàng.
- **Value object:** biểu diễn giá trị theo quy tắc riêng, ví dụ `Money`, `EmailAddress`, `PositiveQuantity`.
- **Domain service hoặc policy:** diễn đạt quyết định nghiệp vụ không thuộc tự nhiên một entity, ví dụ chính sách phân công hoặc tính đủ điều kiện.
- **Domain event:** ghi nhận một sự kiện nghiệp vụ đã xảy ra, ví dụ `TaskCompleted` hoặc `OrderPaid`.

Kiểm thử nên bắt đầu từ hành vi và quy tắc, không bắt đầu từ danh sách getter, setter hoặc từng phương thức private. Một test có giá trị phải chứng minh một điều kiện nghiệp vụ có ý nghĩa.

## Phân biệt unit test Model với kiểm thử tầng MVC

| Mức kiểm thử | Điều cần xác minh | Công cụ hoặc cách làm thường dùng |
|---|---|---|
| Unit test Model | Bất biến, chuyển trạng thái, phép tính và quyết định nghiệp vụ | JUnit, AssertJ, dữ liệu thuần trong bộ nhớ |
| Unit test Domain Service/Policy | Kết quả chính sách theo các dữ kiện miền | JUnit, parameterized test, test case theo bảng |
| Unit test Application Service | Thứ tự điều phối, gọi repository/port và kết quả use case | Fake hoặc mock các port ở ranh giới |
| Controller test | Binding, validation request, route, response và ánh xạ lỗi | Spring MockMvc, security test support |
| Repository integration test | Mapping, truy vấn, transaction và constraint | Database thử nghiệm hoặc Testcontainers |
| Integration/concurrency test | Tính nhất quán khi nhiều thành phần hoặc request cùng hoạt động | Transaction thật, nhiều thread/transaction và database phù hợp |

Một unit test của `Task.complete()` không cần khởi tạo `ApplicationContext`, `DispatcherServlet`, `MockMvc` hay database. Nếu test chỉ muốn xác minh quy tắc “công việc đã hủy không thể hoàn thành”, hãy tạo `Task` trong bộ nhớ, gọi hành vi và kiểm tra kết quả.

Ngược lại, unit test Model không thể chứng minh optimistic locking trong JPA hoạt động đúng hoặc database constraint thực sự ngăn hai transaction ghi trùng. Những bảo đảm đó thuộc kiểm thử tích hợp.

## Thiết kế Model để quy tắc có thể kiểm thử

Một Model dễ kiểm thử thường có các đặc điểm:

- trạng thái được thay đổi qua phương thức mang ý nghĩa nghiệp vụ;
- constructor hoặc factory bảo vệ điều kiện cần đúng ngay khi tạo;
- không để Controller tùy ý gọi setter để bỏ qua quy tắc;
- không phụ thuộc HTTP request, session, template hoặc `SecurityContextHolder`;
- không đọc đồng hồ hệ thống, gọi mạng hoặc truy cập database ẩn bên trong một hành vi thuần;
- phụ thuộc vào abstraction hoặc nhận dữ kiện qua tham số khi cần thông tin bên ngoài;
- trả kết quả hoặc lỗi có ý nghĩa nghiệp vụ để bên gọi xử lý.

Ví dụ, thay vì cung cấp `setStatus(TaskStatus status)`, Model cung cấp `start()`, `complete()` và `cancel()`. Mỗi hành vi kiểm tra trạng thái hiện tại trước khi thay đổi. Test có thể gọi đúng hành vi người dùng yêu cầu và xác minh trạng thái sau thao tác.

## Ví dụ: kiểm thử vòng đời của một công việc

Giả sử ứng dụng quản lý công việc có các trạng thái `OPEN`, `IN_PROGRESS`, `COMPLETED` và `CANCELLED`. Quy tắc được xác định như sau:

- Công việc mới được tạo ở trạng thái `OPEN`.
- Chỉ công việc `OPEN` mới có thể bắt đầu.
- Chỉ công việc `IN_PROGRESS` mới có thể hoàn thành.
- Công việc `OPEN` hoặc `IN_PROGRESS` có thể bị hủy.
- Công việc đã hoàn thành hoặc đã hủy không thể bị hủy lần nữa.
- Công việc đã hủy không thể đổi tên.
- Tiêu đề sau khi tạo hoặc đổi tên phải có nội dung và không vượt quá 120 ký tự.

Đây là hợp đồng nghiệp vụ của ví dụ. Nếu miền của ứng dụng có quy tắc khác, hãy điều chỉnh test theo quy tắc đã thống nhất, không sao chép máy móc trạng thái trong ví dụ.

### Model với hành vi công khai

```java
public enum TaskStatus {
    OPEN,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED
}
```

```java
public record TaskId(long value) {
    public TaskId {
        if (value <= 0) {
            throw new IllegalArgumentException("TaskId phải lớn hơn 0");
        }
    }
}
```

```java
public final class TaskRuleViolation extends RuntimeException {
    public TaskRuleViolation(String message) {
        super(message);
    }
}
```

```java
public final class Task {
    private static final int MAX_TITLE_LENGTH = 120;

    private final TaskId id;
    private String title;
    private TaskStatus status;

    private Task(TaskId id, String title) {
        this.id = Objects.requireNonNull(id);
        this.title = normalizeTitle(title);
        this.status = TaskStatus.OPEN;
    }

    public static Task create(TaskId id, String title) {
        return new Task(id, title);
    }

    public void start() {
        if (status != TaskStatus.OPEN) {
            throw new TaskRuleViolation(
                    "Chỉ công việc đang mở mới có thể bắt đầu");
        }
        status = TaskStatus.IN_PROGRESS;
    }

    public void complete() {
        if (status != TaskStatus.IN_PROGRESS) {
            throw new TaskRuleViolation(
                    "Chỉ công việc đang thực hiện mới có thể hoàn thành");
        }
        status = TaskStatus.COMPLETED;
    }

    public void cancel() {
        if (status == TaskStatus.COMPLETED || status == TaskStatus.CANCELLED) {
            throw new TaskRuleViolation(
                    "Không thể hủy công việc đã kết thúc");
        }
        status = TaskStatus.CANCELLED;
    }

    public void rename(String newTitle) {
        if (status == TaskStatus.CANCELLED) {
            throw new TaskRuleViolation(
                    "Không thể đổi tên công việc đã hủy");
        }
        title = normalizeTitle(newTitle);
    }

    private static String normalizeTitle(String value) {
        if (value == null || value.isBlank()) {
            throw new TaskRuleViolation("Tiêu đề không được để trống");
        }
        String normalized = value.trim();
        if (normalized.length() > MAX_TITLE_LENGTH) {
            throw new TaskRuleViolation("Tiêu đề vượt quá 120 ký tự");
        }
        return normalized;
    }

    public TaskId id() { return id; }
    public String title() { return title; }
    public TaskStatus status() { return status; }
}
```

Ví dụ giả định đã import `java.util.Objects`. Model giữ trạng thái trong field và chỉ thay đổi qua các hành vi có tên nghiệp vụ. Factory `create()` bảo vệ điều kiện lúc khởi tạo; `rename()` tái sử dụng cùng quy tắc chuẩn hóa tiêu đề. Không có setter công khai để mã gọi đặt tùy ý `COMPLETED` hoặc `CANCELLED`.

## Kiểm thử factory và bất biến khi tạo

Test đầu tiên nên xác minh đối tượng được tạo trong trạng thái hợp lệ và giá trị đầu vào được chuẩn hóa theo hợp đồng.

```java
class TaskTest {
    @Test
    void createsOpenTaskAndTrimsTitle() {
        Task task = Task.create(new TaskId(42), "  Viết tài liệu  ");

        assertThat(task.id()).isEqualTo(new TaskId(42));
        assertThat(task.title()).isEqualTo("Viết tài liệu");
        assertThat(task.status()).isEqualTo(TaskStatus.OPEN);
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"   ", "\t", "\n"})
    void rejectsBlankTitle(String title) {
        assertThatThrownBy(() -> Task.create(new TaskId(42), title))
                .isInstanceOf(TaskRuleViolation.class)
                .hasMessage("Tiêu đề không được để trống");
    }

    @Test
    void rejectsTitleLongerThan120Characters() {
        String title = "x".repeat(121);

        assertThatThrownBy(() -> Task.create(new TaskId(42), title))
                .isInstanceOf(TaskRuleViolation.class)
                .hasMessage("Tiêu đề vượt quá 120 ký tự");
    }

    @Test
    void acceptsTitleAtMaximumLength() {
        String title = "x".repeat(120);

        Task task = Task.create(new TaskId(42), title);

        assertThat(task.title()).hasSize(120);
    }
}
```

Ví dụ sử dụng JUnit 5 và AssertJ. Các import thường dùng gồm `org.junit.jupiter.api.Test`, `org.junit.jupiter.params.ParameterizedTest`, `org.junit.jupiter.params.provider.NullAndEmptySource`, `ValueSource` và các assertion của AssertJ.

Kiểm thử dữ liệu biên nên bao gồm:

- giá trị null nếu hợp đồng cho phép đầu vào null đến Model;
- chuỗi rỗng và chuỗi chỉ có khoảng trắng;
- độ dài đúng giới hạn;
- độ dài vượt giới hạn một đơn vị;
- ký tự Unicode nếu giới hạn độ dài có ý nghĩa với người dùng.

Lưu ý `String.length()` trong Java đếm UTF-16 code unit, không phải số grapheme mà người dùng nhìn thấy. Nếu yêu cầu nghiệp vụ giới hạn số ký tự hiển thị, cần chọn cách đếm Unicode phù hợp và viết test cho ký tự có dấu hoặc emoji. Không nên dùng một định nghĩa “ký tự” mơ hồ trong hợp đồng.

## Kiểm thử chuyển trạng thái

Với Model có state machine, cần kiểm tra cả chuyển đổi hợp lệ và chuyển đổi bị từ chối. Chỉ test đường thành công là chưa đủ; phần lớn lỗi trạng thái xuất hiện khi đối tượng ở một trạng thái không dự kiến.

### Kiểm thử chuyển đổi hợp lệ

```java
@Test
void startsOpenTask() {
    Task task = newOpenTask();

    task.start();

    assertThat(task.status()).isEqualTo(TaskStatus.IN_PROGRESS);
}

@Test
void completesTaskInProgress() {
    Task task = newOpenTask();
    task.start();

    task.complete();

    assertThat(task.status()).isEqualTo(TaskStatus.COMPLETED);
}

@Test
void cancelsOpenTask() {
    Task task = newOpenTask();

    task.cancel();

    assertThat(task.status()).isEqualTo(TaskStatus.CANCELLED);
}

@Test
void cancelsTaskInProgress() {
    Task task = newInProgressTask();

    task.cancel();

    assertThat(task.status()).isEqualTo(TaskStatus.CANCELLED);
}
```

Các helper trong test có thể tạo trạng thái ban đầu thông qua hành vi công khai:

```java
private Task newOpenTask() {
    return Task.create(new TaskId(42), "Viết tài liệu");
}

private Task newInProgressTask() {
    Task task = newOpenTask();
    task.start();
    return task;
}

private Task newCompletedTask() {
    Task task = newInProgressTask();
    task.complete();
    return task;
}

private Task newCancelledTask() {
    Task task = newOpenTask();
    task.cancel();
    return task;
}

private Task taskIn(TaskStatus status) {
    Task task = newOpenTask();
    switch (status) {
        case OPEN -> { }
        case IN_PROGRESS -> task.start();
        case COMPLETED -> {
            task.start();
            task.complete();
        }
        case CANCELLED -> task.cancel();
    }
    return task;
}
```

Không nên dùng reflection để sửa field `status` nhằm dựng trạng thái test. Cách đó bỏ qua chính API của Model và có thể tạo ra trạng thái mà hệ thống thật không thể tạo. Dùng factory, fixture builder hoặc hành vi hợp lệ để chuẩn bị trạng thái.

### Kiểm thử chuyển đổi không hợp lệ

```java
@Test
void cannotCompleteOpenTask() {
    Task task = newOpenTask();

    assertThatThrownBy(task::complete)
            .isInstanceOf(TaskRuleViolation.class)
            .hasMessage("Chỉ công việc đang thực hiện mới có thể hoàn thành");

    assertThat(task.status()).isEqualTo(TaskStatus.OPEN);
}

@Test
void cannotStartCompletedTask() {
    Task task = newCompletedTask();

    assertThatThrownBy(task::start)
            .isInstanceOf(TaskRuleViolation.class);

    assertThat(task.status()).isEqualTo(TaskStatus.COMPLETED);
}

@Test
void cannotCancelCompletedTask() {
    Task task = newCompletedTask();

    assertThatThrownBy(task::cancel)
            .isInstanceOf(TaskRuleViolation.class);

    assertThat(task.status()).isEqualTo(TaskStatus.COMPLETED);
}

@Test
void cannotRenameCancelledTask() {
    Task task = newCancelledTask();

    assertThatThrownBy(() -> task.rename("Tiêu đề mới"))
            .isInstanceOf(TaskRuleViolation.class);

    assertThat(task.title()).isEqualTo("Viết tài liệu");
    assertThat(task.status()).isEqualTo(TaskStatus.CANCELLED);
}
```

Khi một hành vi bị từ chối, hãy xác minh trạng thái quan trọng vẫn giữ nguyên. Test chỉ kiểm tra exception có thể bỏ sót lỗi phương thức đã thay đổi một field trước khi ném lỗi. Đặt các kiểm tra trước khi thay đổi trạng thái và kiểm tra cả kết quả sau khi từ chối.

## Dùng bảng chuyển trạng thái để không bỏ sót nhánh

Với state machine, lập ma trận giữa trạng thái hiện tại và hành động. Ma trận làm rõ những tổ hợp cần kiểm thử.

| Trạng thái hiện tại | `start()` | `complete()` | `cancel()` | `rename()` |
|---|---|---|---|---|
| `OPEN` | Thành công → `IN_PROGRESS` | Từ chối | Thành công → `CANCELLED` | Thành công |
| `IN_PROGRESS` | Từ chối | Thành công → `COMPLETED` | Thành công → `CANCELLED` | Thành công |
| `COMPLETED` | Từ chối | Từ chối | Từ chối | Thành công theo quy tắc ví dụ |
| `CANCELLED` | Từ chối | Từ chối | Từ chối | Từ chối |

Ma trận này là một phần của đặc tả nghiệp vụ. Khi thêm trạng thái mới như `BLOCKED` hoặc `ARCHIVED`, hãy cập nhật ma trận và test tương ứng. Nếu một hành động không được định nghĩa cho trạng thái nào đó, cần quyết định rõ là từ chối, không làm gì (idempotent) hay trả kết quả đã hoàn tất trước đó.

Có thể dùng parameterized test để kiểm tra nhiều trạng thái bị từ chối:

```java
@ParameterizedTest
@EnumSource(value = TaskStatus.class,
        names = {"OPEN", "COMPLETED", "CANCELLED"})
void completeIsRejectedOutsideInProgress(TaskStatus initialStatus) {
    Task task = taskIn(initialStatus);

    assertThatThrownBy(task::complete)
            .isInstanceOf(TaskRuleViolation.class);
    assertThat(task.status()).isEqualTo(initialStatus);
}
```

`taskIn(initialStatus)` nên dựng từng trạng thái qua hành vi công khai. Ví dụ, `OPEN` không cần thao tác, `IN_PROGRESS` gọi `start()`, `COMPLETED` gọi `start()` rồi `complete()`, còn `CANCELLED` gọi `cancel()`. Không thêm setter chỉ để phục vụ test.

## Kiểm thử Value Object

Value object thường có thể kiểm thử bằng một số lượng nhỏ unit test vì nó không cần repository hoặc vòng đời entity. Hãy kiểm tra:

- điều kiện hợp lệ khi tạo;
- chuẩn hóa giá trị nếu hợp đồng quy định;
- equality và hash code dựa trên giá trị;
- phép toán không làm mất bất biến;
- các trường hợp biên và giá trị null.

Ví dụ `PositiveQuantity`:

```java
public record PositiveQuantity(int value) {
    public PositiveQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn 0");
        }
    }
}
```

```java
class PositiveQuantityTest {
    @Test
    void acceptsPositiveQuantity() {
        assertThat(new PositiveQuantity(1).value()).isEqualTo(1);
    }

    @ParameterizedTest
    @ValueSource(ints = {0, -1, -100})
    void rejectsZeroAndNegativeValues(int value) {
        assertThatThrownBy(() -> new PositiveQuantity(value))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Với `Money`, test nên kiểm tra không cộng hai loại tiền tệ khác nhau nếu miền không cho phép, quy tắc làm tròn, độ chính xác thập phân và hành vi với số âm. Dùng `BigDecimal` thay cho `double` khi biểu diễn số tiền cần độ chính xác thập phân. Test nên bao gồm giá trị sát ranh giới, ví dụ số tiền bằng 0, nhỏ hơn 0 và số chữ số thập phân vượt quy định.

Với `EmailAddress`, không nên cố kiểm tra mọi trường hợp của chuẩn email bằng một regex tự viết rồi xem đó là đặc tả hoàn chỉnh. Hãy xác định chính sách sản phẩm chấp nhận, kiểm tra các trường hợp thực tế và dùng cơ chế xác minh địa chỉ qua email khi cần chứng minh quyền sở hữu.

## Kiểm thử Domain Service và Policy

Một quy tắc có thể phụ thuộc nhiều đối tượng mà không thuộc tự nhiên một entity. Khi đó, domain service hoặc policy có thể nhận dữ kiện miền đã được tải và trả quyết định.

Ví dụ chính sách giao việc:

```java
public record AssignmentFacts(
        boolean projectActive,
        boolean assigneeIsMember,
        boolean hasRequiredSkill,
        int currentOpenTasks,
        int openTaskLimit) {
}
```

```java
public final class TaskAssignmentPolicy {
    public void ensureAllowed(AssignmentFacts facts) {
        if (!facts.projectActive()) {
            throw new TaskRuleViolation("Dự án đã đóng");
        }
        if (!facts.assigneeIsMember()) {
            throw new TaskRuleViolation("Người được giao không thuộc dự án");
        }
        if (!facts.hasRequiredSkill()) {
            throw new TaskRuleViolation("Thiếu kỹ năng cần thiết");
        }
        if (facts.currentOpenTasks() >= facts.openTaskLimit()) {
            throw new TaskRuleViolation("Đã đạt giới hạn công việc");
        }
    }
}
```

Policy này thuần theo các dữ kiện đầu vào, nên test không cần mock database hoặc gọi dịch vụ bên ngoài:

```java
class TaskAssignmentPolicyTest {
    private final TaskAssignmentPolicy policy = new TaskAssignmentPolicy();

    @Test
    void allowsAssignmentWhenAllConditionsAreSatisfied() {
        AssignmentFacts facts = new AssignmentFacts(
                true, true, true, 2, 5);

        assertThatCode(() -> policy.ensureAllowed(facts))
                .doesNotThrowAnyException();
    }

    @Test
    void rejectsAssignmentToInactiveProject() {
        AssignmentFacts facts = new AssignmentFacts(
                false, true, true, 2, 5);

        assertThatThrownBy(() -> policy.ensureAllowed(facts))
                .isInstanceOf(TaskRuleViolation.class)
                .hasMessage("Dự án đã đóng");
    }

    @Test
    void rejectsAssigneeWhoIsNotProjectMember() {
        AssignmentFacts facts = new AssignmentFacts(
                true, false, true, 2, 5);

        assertThatThrownBy(() -> policy.ensureAllowed(facts))
                .isInstanceOf(TaskRuleViolation.class);
    }

    @Test
    void rejectsAssigneeAtOpenTaskLimit() {
        AssignmentFacts facts = new AssignmentFacts(
                true, true, true, 5, 5);

        assertThatThrownBy(() -> policy.ensureAllowed(facts))
                .isInstanceOf(TaskRuleViolation.class);
    }
}
```

Ngoài các trường hợp riêng, hãy kiểm tra ranh giới của hạn mức: `currentOpenTasks = limit - 1` được chấp nhận; bằng `limit` bị từ chối; lớn hơn `limit` cũng bị từ chối. Nếu dữ kiện âm hoặc giới hạn không hợp lệ có thể xuất hiện, cần quy định nơi bảo vệ và thêm test.

Application service chịu trách nhiệm tải `Project`, `User` và `Task` từ repository, xây dựng `AssignmentFacts`, gọi policy rồi cập nhật Model. Test policy không chứng minh truy vấn đã tải đúng dữ liệu; test application service hoặc integration test cần xác minh phần phối hợp đó.

## Kiểm thử quy tắc phụ thuộc thời gian

Nếu quy tắc liên quan thời hạn, ngày hết hạn hoặc thời gian khóa, không nên gọi `LocalDate.now()` hoặc `Instant.now()` trực tiếp ở nhiều nơi trong Model. Đồng hồ hệ thống khiến test phụ thuộc thời điểm chạy và có thể thất bại ở ranh giới ngày/giờ.

Hãy truyền thời gian vào hành vi hoặc inject `Clock` ở ranh giới phù hợp. Ví dụ:

```java
public boolean isOverdue(Clock clock) {
    return dueDate != null
            && LocalDate.now(clock).isAfter(dueDate)
            && status != TaskStatus.COMPLETED;
}
```

```java
@Test
void taskBecomesOverdueAfterDueDate() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-05-11T00:00:00Z"),
            ZoneOffset.UTC);
    Task task = taskWithDueDate(LocalDate.of(2026, 5, 10));

    assertThat(task.isOverdue(clock)).isTrue();
}
```

Test nên bao gồm đúng thời điểm đến hạn, trước hạn và sau hạn; xác định rõ múi giờ nghiệp vụ. Nếu hạn chót tính theo ngày địa phương, hãy dùng `ZoneId` được quy định thay vì mặc định UTC hoặc múi giờ máy chủ.

## Kiểm thử phép tính và quy tắc kết hợp

Một số Model thực hiện phép tính có nhiều điều kiện: giá sau giảm, thuế, phí, hạn mức hoặc phân bổ số lượng. Với những quy tắc này, test cần thể hiện rõ đầu vào, đơn vị, cách làm tròn và thứ tự áp dụng.

Ví dụ với giá tiền:

- xác định loại tiền tệ;
- xác định giảm giá tính theo phần trăm hay số tiền cố định;
- xác định thứ tự áp dụng giảm giá, thuế và phí;
- quy định số chữ số thập phân và chế độ làm tròn;
- xử lý tổng bằng 0, âm hoặc vượt giới hạn.

Nên viết test theo ví dụ nghiệp vụ có thể kiểm tra độc lập bằng phép tính tay hoặc bảng quyết định. Với các tổ hợp nhiều điều kiện, bảng test giúp phát hiện trường hợp tương tác mà từng test đơn lẻ có thể bỏ sót.

| Điều kiện | Giá trị ví dụ | Điều cần xác minh |
|---|---|---|
| Không giảm giá | 100.00 | Tổng bằng giá gốc cộng thuế/phí theo quy tắc |
| Giảm giá tối đa | Mức giảm bằng giới hạn | Không vượt mức giảm được phép |
| Giảm giá vượt giới hạn | Mức giảm lớn hơn giới hạn | Bị giới hạn hoặc từ chối theo chính sách |
| Tổng bằng 0 | Đơn hàng miễn phí | Không tạo khoản thanh toán âm |
| Loại tiền khác nhau | VND và USD | Không cộng trực tiếp nếu chưa có quy tắc chuyển đổi |

Không chỉ assert một kết quả số cuối cùng. Khi cần, kiểm tra breakdown như subtotal, discount, tax và total để biết quy tắc nào sai.

## Kiểm thử bất biến của Aggregate

Aggregate root bảo vệ tính nhất quán bên trong một ranh giới nghiệp vụ. Ví dụ, `Order` có thể quản lý danh sách `OrderLine`, tổng tiền và trạng thái. Không nên để mã bên ngoài thêm dòng hàng trực tiếp vào collection rồi quên cập nhật tổng hoặc kiểm tra số lượng.

Test aggregate nên kiểm tra:

- chỉ aggregate root cung cấp hành vi thay đổi trạng thái;
- mỗi hành vi giữ các bất biến giữa root và các đối tượng con;
- thao tác thất bại không để lại trạng thái một phần;
- quy tắc tổng hợp được tính lại hoặc duy trì đúng;
- các trạng thái kết thúc ngăn những thay đổi không được phép.

Ví dụ, nếu `Order.addLine(product, quantity)` phải kiểm tra đơn hàng còn ở trạng thái nháp và số lượng dương, test cần xác minh cả dòng hàng và tổng đơn hàng sau khi thêm. Khi thêm thất bại, test xác minh danh sách và tổng vẫn giữ nguyên.

Không nên tạo một test cho từng getter của `OrderLine`. Hãy tập trung vào hợp đồng aggregate mà các client bên ngoài có thể sử dụng.

## Kiểm thử lỗi nghiệp vụ và kết quả từ chối

Model có thể biểu diễn việc từ chối bằng exception miền, kiểu kết quả hoặc một dạng lỗi có cấu trúc. Cách chọn phụ thuộc ngôn ngữ và kiến trúc, nhưng test cần xác minh loại lỗi và trạng thái sau khi từ chối.

Nếu dùng exception:

- kiểm tra đúng loại exception nghiệp vụ;
- kiểm tra mã lỗi hoặc thông điệp ổn định nếu chúng thuộc hợp đồng;
- xác minh không có thay đổi trạng thái ngoài ý muốn;
- tránh kiểm tra stack trace hoặc chi tiết triển khai không thuộc hợp đồng.

Nếu dùng kiểu kết quả như `Result<Success, DomainError>`, hãy kiểm tra cả nhánh thành công và từng loại lỗi. Không nên chỉ kiểm tra kết quả là `false` nếu caller cần biết lý do để phản hồi hoặc xử lý tiếp.

Không dùng exception để thay thế validation cú pháp đơn giản ở ranh giới web. Ví dụ, chuỗi ngày không parse được thường được phát hiện trong binding/DTO validation; còn ngày hợp lệ về định dạng nhưng vi phạm quy tắc miền có thể bị Model hoặc policy từ chối.

## Kiểm thử sự kiện miền

Nếu hành vi Model phát ra domain event, test có thể xác minh sự kiện được tạo đúng khi hành động thành công và không được phát ra khi hành động bị từ chối.

Ví dụ, khi `Task.complete()` thành công, aggregate có thể ghi nhận `TaskCompleted(taskId, completedAt)`. Test nên kiểm tra:

- loại sự kiện;
- định danh aggregate;
- dữ liệu nghiệp vụ quan trọng;
- thời điểm hoặc actor nếu hợp đồng sự kiện yêu cầu;
- không phát sự kiện hai lần nếu hành vi không cho phép lặp.

Không nên test cách event được publish qua Kafka hoặc message broker trong unit test Model. Unit test chỉ kiểm tra sự kiện miền được tạo; adapter hoặc application service chịu trách nhiệm publish và cần kiểm thử ở mức khác.

## Tránh phụ thuộc ngoài trong unit test Model

Một unit test Model nên chạy nhanh và xác định. Hạn chế các phụ thuộc sau:

- database hoặc ORM;
- HTTP client, email provider hoặc message broker;
- thời gian hệ thống thực;
- số ngẫu nhiên không được kiểm soát;
- filesystem hoặc thư mục tạm không cần thiết;
- Spring `ApplicationContext` nếu quy tắc không cần framework.

Nếu Model cần một giá trị bên ngoài như thời gian, tỷ giá hoặc chính sách tải từ cấu hình, hãy truyền dữ kiện qua tham số hoặc abstraction. Test có thể dùng giá trị cố định để kết quả lặp lại được.

Không mock chính đối tượng đang kiểm thử hoặc mock mọi method của entity. Mock quá sâu thường kiểm tra cách cài đặt thay vì hành vi. Với Model thuần, tạo object thật và gọi hành vi thật; chỉ fake dependency ở ranh giới khi có lý do.

## Thiết kế test data và fixture

Test data nên nhỏ, rõ và thể hiện điều kiện cần thiết cho quy tắc. Tránh tạo một fixture khổng lồ có hàng chục thuộc tính không liên quan.

Có thể dùng factory riêng trong test:

```java
private Task taskNamed(String title) {
    return Task.create(new TaskId(42), title);
}
```

Với aggregate phức tạp, một test data builder có thể giúp tạo trạng thái hợp lệ. Builder nên gọi API công khai hoặc factory miền, không sửa field private bằng reflection. Nếu builder cho phép tạo trạng thái bất khả thi, nó có thể che giấu lỗi thiết kế.

Mỗi test nên độc lập: không phụ thuộc thứ tự chạy, dữ liệu static mutable hoặc trạng thái do test trước để lại. Dùng ID cố định trong unit test thường tốt hơn ID ngẫu nhiên vì kết quả dễ đọc và tái hiện.

## Quy ước đặt tên và cấu trúc test

Tên test nên mô tả điều kiện và kết quả mong đợi. Một số dạng phổ biến:

- `createsOpenTaskWhenTitleIsValid()`
- `rejectsBlankTitle()`
- `completesTaskInProgress()`
- `rejectsCompletionWhenTaskIsOpen()`
- `keepsStateUnchangedWhenCancellationIsRejected()`

Có thể dùng cấu trúc Arrange–Act–Assert:

1. **Arrange:** tạo Model và chuẩn bị trạng thái ban đầu.
2. **Act:** gọi đúng hành vi đang kiểm thử.
3. **Assert:** xác minh trạng thái, kết quả hoặc lỗi theo hợp đồng.

Mỗi test nên có một lý do thất bại rõ. Nếu một test kiểm tra nhiều hành vi không liên quan, hãy tách để khi lỗi xảy ra có thể định vị quy tắc bị vi phạm.

## Bao phủ quy tắc bằng ma trận kiểm thử

Trước khi viết test, liệt kê các quy tắc và tình huống tương ứng. Ví dụ cho `Task`:

| Quy tắc | Trường hợp hợp lệ | Trường hợp bị từ chối | Trạng thái sau lỗi |
|---|---|---|---|
| Tiêu đề khi tạo | Có nội dung, tối đa 120 ký tự | Null, rỗng, vượt giới hạn | Không có đối tượng được tạo |
| Bắt đầu | `OPEN` | `IN_PROGRESS`, `COMPLETED`, `CANCELLED` | Giữ nguyên trạng thái |
| Hoàn thành | `IN_PROGRESS` | `OPEN`, `COMPLETED`, `CANCELLED` | Giữ nguyên trạng thái |
| Hủy | `OPEN`, `IN_PROGRESS` | `COMPLETED`, `CANCELLED` | Giữ nguyên trạng thái |
| Đổi tên | Trạng thái không bị hủy và tiêu đề hợp lệ | `CANCELLED`, tiêu đề rỗng hoặc quá dài | Giữ nguyên tiêu đề và trạng thái |

Ma trận giúp nhìn ra trường hợp thiếu, nhưng không phải mọi tổ hợp đều cần một test riêng nếu chúng có cùng quy tắc và có thể dùng parameterized test. Ưu tiên trường hợp biên, nhánh điều kiện và những thao tác có hậu quả lớn.

## Khi nào cần Property-based Testing?

Với quy tắc có miền đầu vào lớn hoặc nhiều phép toán, property-based testing có thể sinh nhiều giá trị để kiểm tra một tính chất tổng quát thay vì chỉ vài ví dụ cố định.

Ví dụ tính chất:

- chuẩn hóa tiêu đề không tạo ra chuỗi rỗng nếu đầu vào hợp lệ;
- số lượng dương sau khi nhân hoặc cộng vẫn tuân theo giới hạn đã định;
- tổng các dòng hàng bằng tổng được aggregate công bố;
- phép cộng `Money` giữ nguyên currency và không làm mất độ chính xác theo quy tắc.

Thư viện như jqwik có thể tích hợp với JUnit 5 để sinh dữ liệu. Property test không thay thế các test ví dụ dễ đọc; nó bổ sung khả năng khám phá giá trị biên và tổ hợp bất ngờ. Khi tìm được lỗi, hãy lưu seed hoặc rút gọn thành một regression test cụ thể để lỗi không tái xuất hiện.

## Khi nào cần Mutation Testing?

Code coverage cho biết test đã chạy qua dòng hoặc nhánh nào, nhưng không chứng minh assertion đủ mạnh. Mutation testing thay đổi nhỏ trong mã, ví dụ đổi `>=` thành `>`, đảo điều kiện hoặc bỏ một phép kiểm tra, rồi xem test có phát hiện thay đổi đó không.

Ví dụ, nếu quy tắc giới hạn công việc là `currentOpenTasks >= openTaskLimit`, test chỉ dùng giá trị thấp hơn hạn mức có thể vẫn xanh khi ai đó đổi toán tử thành `>`. Thêm test đúng bằng hạn mức giúp phát hiện lỗi biên.

Mutation testing có thể hữu ích với Model chứa quy tắc quan trọng. Tuy nhiên, không cần chạy cho mọi module hoặc xem mutation score là mục tiêu duy nhất. Hãy dùng nó để tìm assertion yếu trong phần nghiệp vụ có rủi ro cao.

## Phân biệt unit test Model với kiểm thử transaction và concurrency

Một quy tắc có thể đúng trong một instance Model nhưng vẫn bị vi phạm khi nhiều request cùng thực hiện. Ví dụ, chính sách không cho một người vượt quá năm công việc đang mở:

1. Request A đọc số lượng hiện tại là bốn.
2. Request B cũng đọc số lượng là bốn.
3. Cả hai cùng vượt qua policy vì `4 < 5`.
4. Cả hai cùng lưu thêm một công việc.
5. Kết quả có sáu công việc, vượt hạn mức.

Unit test của `TaskAssignmentPolicy` vẫn đúng vì mỗi lần kiểm tra độc lập. Lỗi nằm ở ranh giới đọc/ghi đồng thời. Cần kiểm thử tích hợp với transaction và cơ chế bảo vệ phù hợp như khóa, optimistic version, constraint hoặc cập nhật nguyên tử.

| Câu hỏi | Unit test Model có đủ không? | Kiểm thử bổ sung |
|---|---|---|
| `complete()` từ `OPEN` có bị từ chối? | Có | Không cần database |
| `Money` làm tròn theo quy tắc? | Có | Không cần database |
| Repository ánh xạ status đúng? | Không | Repository integration test |
| Transaction rollback khi bước lưu thất bại? | Không | Integration test với transaction thật |
| Hai request không thể vượt hạn mức cùng lúc? | Không | Concurrency test với database và cơ chế đồng bộ thật |
| Controller trả 409 khi Model từ chối? | Không | Controller/HTTP integration test |

## Kiểm thử lỗi và ánh xạ response ở MVC

Model nên trả lỗi miền có ý nghĩa; Controller hoặc exception handler chuyển lỗi đó thành phản hồi theo giao thức.

Ví dụ:

- `TaskRuleViolation` do trạng thái không cho phép có thể ánh xạ thành thông báo nghiệp vụ hoặc HTTP 409;
- dữ liệu form sai định dạng có thể được xử lý bởi binding/validation và trả lại trang cùng lỗi trường;
- không tìm thấy công việc có thể ánh xạ thành 404;
- lỗi hạ tầng không nên bị trình bày như lỗi nghiệp vụ.

Không kiểm tra HTTP status trong unit test Model. Hãy kiểm tra lỗi miền ở unit test, rồi kiểm tra ánh xạ lỗi ở Controller test hoặc test `@ControllerAdvice`. Việc tách này giúp Model không phụ thuộc Spring MVC.

## Những cách kiểm thử dễ gây hiểu nhầm

- **Chỉ kiểm tra getter và setter:** test có thể đạt coverage cao nhưng không chứng minh quy tắc nghiệp vụ. Kiểm tra hành vi và trạng thái sau hành động.
- **Dựng trạng thái bằng reflection:** test tạo được trạng thái mà hệ thống thật không thể tạo. Dùng factory hoặc hành vi công khai.
- **Mock entity đang kiểm thử:** test kiểm tra tương tác giả thay vì hành vi Model thật. Tạo object thực trong bộ nhớ.
- **Chỉ kiểm tra exception:** bỏ sót việc trạng thái đã bị thay đổi một phần trước khi lỗi xảy ra. Xác minh trạng thái sau khi từ chối.
- **Chỉ test đường thành công:** không phát hiện các chuyển trạng thái trái phép. Dùng ma trận trạng thái và test ranh giới.
- **Dùng thời gian hoặc random thật:** test chập chờn và khó tái hiện. Cố định Clock, seed hoặc dữ liệu đầu vào.
- **Khởi tạo toàn bộ Spring context cho Model thuần:** test chậm và gắn quy tắc với framework không cần thiết. Dùng unit test trực tiếp.
- **Đặt assertion vào chi tiết private:** refactor nội bộ làm test hỏng dù hành vi không đổi. Assert qua API công khai.
- **Dùng coverage làm bằng chứng duy nhất:** dòng đã chạy không có nghĩa kết quả đã được kiểm tra. Xem xét mutation testing và chất lượng assertion.
- **Cho rằng unit test chứng minh concurrency:** test tuần tự không thể xác nhận transaction/locking. Bổ sung kiểm thử tích hợp đồng thời.

## Quy trình xây dựng bộ test cho một Model

Khi thêm hoặc thay đổi quy tắc nghiệp vụ, có thể thực hiện theo trình tự:

1. **Đọc hợp đồng Model:** xác định entity, value object, aggregate và policy có liên quan.
2. **Liệt kê bất biến:** điều kiện phải đúng khi tạo và sau mỗi hành vi.
3. **Vẽ ma trận trạng thái:** ghi hành động nào được phép hoặc bị từ chối ở từng trạng thái.
4. **Xác định dữ liệu biên:** null, rỗng, giới hạn, giá trị ngay dưới/trên ngưỡng và tổ hợp điều kiện.
5. **Viết test hành vi thành công:** xác minh trạng thái và kết quả công khai.
6. **Viết test từ chối:** xác minh loại lỗi và trạng thái không bị thay đổi ngoài ý muốn.
7. **Kiểm thử policy/domain service:** bao phủ các nhánh quyết định và giới hạn.
8. **Kiểm tra tính xác định:** cố định thời gian, dữ liệu và nguồn ngẫu nhiên; không gọi hệ thống ngoài.
9. **Bổ sung kiểm thử đúng tầng:** repository, transaction, HTTP và concurrency được kiểm thử ở ranh giới riêng.
10. **Đánh giá chất lượng assertion:** xem test có thất bại nếu điều kiện nghiệp vụ bị đảo hoặc bỏ đi không.

## Checklist khi review test quy tắc nghiệp vụ

- Test mô tả một quy tắc nghiệp vụ cụ thể và có tên dễ hiểu.
- Model được tạo qua factory hoặc API hợp lệ, không sửa field private bằng reflection.
- Có test đường thành công và các trạng thái/giá trị bị từ chối.
- Có test đúng tại ranh giới, không chỉ giá trị điển hình.
- Khi hành động thất bại, trạng thái quan trọng vẫn được giữ nguyên.
- Value object kiểm tra bất biến, equality và phép toán cần thiết.
- Domain service/policy được kiểm thử theo các dữ kiện và nhánh quyết định.
- Test không phụ thuộc database, HTTP, Spring context hoặc thời gian hệ thống nếu không cần.
- Lỗi miền được kiểm tra riêng với HTTP response.
- Các bảo đảm transaction, persistence và concurrency có kiểm thử tích hợp tương ứng.
- Assertion kiểm tra kết quả nghiệp vụ thay vì chi tiết cài đặt.

Kiểm thử quy tắc nghiệp vụ của Model giúp xác nhận các hành vi quan trọng được bảo vệ ngay tại nơi sở hữu trạng thái và bất biến. Unit test thuần nên kiểm tra factory, value object, chuyển trạng thái, aggregate và domain policy bằng dữ liệu xác định. Controller, repository và transaction được kiểm thử ở ranh giới riêng. Khi kết hợp ma trận trạng thái, dữ liệu biên và kiểm thử tích hợp đúng chỗ, bộ test sẽ phát hiện cả lỗi quy tắc lẫn lỗi phối hợp mà không làm Model phụ thuộc vào giao diện web.
