# Dùng guard cho quyền hoặc trạng thái trong pattern switch (Java 21)

## 1. Bài toán: phân phối command phải kiểm tra quyền và trạng thái

Một hệ thống nghiệp vụ thường nhận nhiều **command** như tạo công việc, gửi duyệt, phê duyệt hoặc hủy công việc. Mỗi command có dữ liệu riêng, nhưng **không phải ai cũng có thể thực hiện mọi lệnh** và **không phải trạng thái nào cũng chấp nhận mọi thao tác**.

Ví dụ:

- Người được cấp quyền `CREATE` mới được tạo công việc.
- Chủ sở hữu công việc hoặc người có quyền `SUBMIT` mới được gửi duyệt.
- Người có quyền `APPROVE` được duyệt công việc đã `SUBMITTED`, nhưng không được tự duyệt công việc của chính mình.
- Người có quyền `CANCEL` được hủy công việc đang `DRAFT` hoặc `SUBMITTED`, nhưng không được hủy công việc đã `APPROVED` hoặc `CANCELLED`.

Nếu đặt tất cả logic vào một chuỗi `if / else` dài, mã dễ lẫn việc **xác định loại command**, **kiểm tra quyền**, **kiểm tra trạng thái** và **thực hiện tác vụ**. Với **pattern matching for switch** của Java 21, ta có thể dùng **record patterns** để nhận dạng command và `when` guard để diễn đạt quy tắc trước khi trả về quyết định.

Mục tiêu học tập:

1. Mô hình hóa các command bằng `sealed interface` và `record`.
2. Hiểu guard `when` chạy **sau khi pattern khớp** và trước khi nhánh được chọn.
3. Phân biệt kiểm tra quyền (authorization), kiểm tra dữ liệu và kiểm tra trạng thái.
4. Sắp xếp các nhánh để **từ chối trước**, tránh lộ thông tin và không để case rộng che case hẹp.
5. Xử lý `null`, thiếu quyền, chủ sở hữu, trạng thái sai và quy tắc cấm tự phê duyệt.
6. Kiểm thử quyết định với Java 21, bao gồm cả các đường `DENY` và thứ tự ưu tiên lỗi.
7. Hiểu giới hạn bảo mật: guard không thay thế xác thực người dùng, transaction hay kiểm tra trạng thái tại thời điểm ghi dữ liệu.

**Phiên bản:** `record patterns` (JEP 440) và `pattern matching for switch` (JEP 441) trở thành tính năng chính thức trong **Java 21**, không cần `--enable-preview`. Các đoạn code runnable sử dụng JDK 21 trở lên.

## 2. Ba tầng quyết định cần tách bạch

Trước khi viết switch, hãy phân loại các điều kiện:

| Tầng | Câu hỏi | Ví dụ | Kết quả khi thất bại |
| --- | --- | --- | --- |
| Authentication / nhận diện actor | Đã có danh tính được hệ thống xác thực chưa? | `actor != null` trong demo | `UNAUTHENTICATED` |
| Authorization / quyền hạn | Danh tính có quyền thao tác trên tài nguyên này không? | `actor.can(APPROVE)` hoặc là chủ sở hữu | `FORBIDDEN` |
| Business state / trạng thái | Command có hợp lệ tại trạng thái hiện tại không? | Chỉ duyệt khi `state == SUBMITTED` | `INVALID_STATE` |
| Business constraint / quy tắc bổ sung | Có xung đột với quy tắc riêng không? | Không được tự phê duyệt | `SELF_APPROVAL` |
| Input validity / dữ liệu | Command và tài nguyên có đủ dữ liệu cần thiết không? | Task không null, ID không blank | `INVALID_INPUT` |

Trong hệ thống thật, xác thực actor là trách nhiệm của tầng HTTP/gRPC, session, JWT verifier hoặc security context đáng tin. Ví dụ chỉ mô phỏng bằng `Actor` để tập trung vào **case study command**; không coi một `Actor` tùy ý do client gửi là bằng chứng người dùng đã đăng nhập hoặc được cấp quyền.

**Quy tắc quan trọng:** quyền hạn và trạng thái là hai thứ khác nhau. Một người có quyền `APPROVE` vẫn không được duyệt công việc đang ở `DRAFT`. Ngược lại, công việc ở `SUBMITTED` không làm mọi người đều có quyền duyệt.

## 3. Mô hình domain: command, actor và trạng thái

Ta định nghĩa:

```java
enum Permission { CREATE, SUBMIT, APPROVE, CANCEL }
enum State { DRAFT, SUBMITTED, APPROVED, CANCELLED }
```

Actor có ID và tập quyền:

```java
record Actor(String id, java.util.Set<Permission> permissions) {
    Actor {
        java.util.Objects.requireNonNull(id, "actor id");
        permissions = java.util.Set.copyOf(
            java.util.Objects.requireNonNull(permissions, "permissions")
        );
    }
    boolean can(Permission permission) {
        return permissions.contains(permission);
    }
}
```

Điểm đáng chú ý: `Set.copyOf(...)` tạo một tập quyền không thể sửa qua tham chiếu collection đầu vào và loại bỏ phần tử null theo hợp đồng của API. Điều này giúp tránh việc một đoạn code khác vô tình sửa tập quyền ngay sau khi tạo Actor. Nó **không xác thực nguồn gốc** quyền; trong production, quyền vẫn phải được xây dựng từ nguồn dữ liệu đáng tin.

Task có ID, chủ sở hữu và trạng thái:

```java
record Task(String id, String ownerId, State state) {
    Task {
        java.util.Objects.requireNonNull(id, "task id");
        java.util.Objects.requireNonNull(ownerId, "owner id");
        java.util.Objects.requireNonNull(state, "state");
    }
}
```

Constructor trên ngăn `id`, `ownerId` và `state` null. Đây là ràng buộc kỹ thuật cơ bản; mã chưa xác thực ID tồn tại trong database hoặc thuộc cùng tenant. Một `Task` được dựng từ input không đáng tin **không tự động** trở thành tài nguyên có thẩm quyền để quyết định quyền.

Các command:

```java
sealed interface Command permits Create, Submit, Approve, Cancel {}

record Create(String taskId) implements Command {}
record Submit(Task task) implements Command {}
record Approve(Task task) implements Command {}
record Cancel(Task task) implements Command {}
```

Một `sealed interface` giới hạn các implementor được phép trực tiếp. Các record `Create`, `Submit`, `Approve`, `Cancel` là các dạng command cụ thể. Nhờ có hệ kiểu đóng, một `switch expression` trên `Command` có thể bao phủ đủ các subtype **không cần `default`**, giúp compiler nhắc khi thêm loại command mới.

Đừng nhầm `Command` ở đây với Java `Runnable` hoặc một pattern thiết kế khác chỉ vì cùng từ “command”. Trong bài, đó là kiểu dữ liệu nghiệp vụ mô tả **ý định** cần được xét duyệt trước khi thực thi.

## 4. Bảng quyền và chuyển trạng thái

Trước khi viết `when`, nên mô tả luật thành bảng. Đây là nền tảng cho code review và tests.

| Command | Ai có thể yêu cầu? | Trạng thái/đầu vào cần thiết | Kết quả khi được chấp nhận |
| --- | --- | --- | --- |
| `Create(taskId)` | Có quyền `CREATE` | `taskId` không null, không blank | `ALLOW CREATE` |
| `Submit(task)` | Có quyền `SUBMIT` **hoặc** là chủ sở hữu | Task tồn tại, đang `DRAFT` | `ALLOW SUBMIT` |
| `Approve(task)` | Có quyền `APPROVE` và **không phải chủ sở hữu** | Task tồn tại, đang `SUBMITTED` | `ALLOW APPROVE` |
| `Cancel(task)` | Có quyền `CANCEL` | Task tồn tại, đang `DRAFT` hoặc `SUBMITTED` | `ALLOW CANCEL` |

Trong demo, việc tạo task chưa được triển khai; `ALLOW CREATE` là **quyết định cho phép**, không phải thông báo đã ghi một record xuống database. Tương tự, `ALLOW APPROVE` không chuyển `Task.state` thành `APPROVED`. Đây là sự tách bạch có chủ đích giữa **kiểm tra** và **thực thi**.

Các quyết định từ chối sử dụng mã lỗi:

- `UNAUTHENTICATED`: chưa có actor.
- `INVALID_COMMAND`: command null.
- `FORBIDDEN`: actor không được phép thực hiện command.
- `INVALID_INPUT`: dữ liệu command không đủ.
- `INVALID_STATE`: trạng thái không cho phép thao tác.
- `SELF_APPROVAL`: vi phạm nguyên tắc phân tách trách nhiệm.

Thứ tự ưu tiên lỗi ảnh hưởng hành vi quan sát được. Ví dụ, với `Approve`, ta kiểm tra **quyền trước**, rồi mới kiểm tra dữ liệu và trạng thái để không trả thông tin trạng thái nghiệp vụ cho một actor không có quyền `APPROVE`. Trong ứng dụng thật, thậm chí việc phân biệt tài nguyên tồn tại hay không có thể phải được che khỏi người không có quyền.

## 5. Cơ chế guard when của pattern switch

Với Java 21, `case` có thể gồm một pattern và một guard:

```java
case Approve(var task) when !actor.can(Permission.APPROVE)
        -> Decision.deny("FORBIDDEN");
```

Trình tự hiểu:

1. `switch (command)` đánh giá **selector** là một giá trị `Command`.
2. Pattern `Approve(var task)` kiểm tra command có phải record `Approve` không.
3. Nếu pattern khớp, biến `task` được ràng buộc từ component của record.
4. Java đánh giá `when !actor.can(Permission.APPROVE)`.
5. Nếu guard true, case đó được chọn và trả `DENY FORBIDDEN`.
6. Nếu guard false, Java xét các case tiếp theo. **Không phải guard false nghĩa là toàn bộ command bị từ chối**; phải có case khác xử lý.

Guard `when` là một biểu thức boolean chạy trong phạm vi biến pattern được ràng buộc. Ví dụ:

```java
case Submit(var task) when task.state() != State.DRAFT
        -> Decision.deny("INVALID_STATE");
```

Biểu thức trên chỉ an toàn nếu các nhánh trước đã loại `task == null` hoặc bản thân guard kiểm tra null. Nếu `task` null, gọi `task.state()` ném `NullPointerException`. Trong code hoàn chỉnh, nhánh `Submit(var task) when task == null` được đặt trước.

### Guard khác với guard clause

**Guard của switch**: điều kiện sau `when` quyết định liệu một case có được chọn.

**Guard clause**: câu `if (!condition) return ...;` dùng để thoát sớm khỏi phương thức hoặc block.

Hai kỹ thuật có thể phối hợp: kiểm tra actor/command null bằng guard clauses trước, rồi dùng `when` trong switch để diễn đạt luật riêng của mỗi loại command. Đây là lựa chọn của bài: đừng cố đẩy mọi kiểm tra, kể cả sự hiện diện của actor, vào những case phức tạp.

### Pattern match không đồng nghĩa thành công

Nếu `command` là `Approve(task)`, pattern `Approve(var task)` khớp **dù actor không có quyền**. Quyền chỉ được xét bằng `when`. Tương tự, một record có thể khớp kiểu nhưng chứa `task == null`; `var task` vẫn có thể ràng buộc null. Vì vậy cần test cả **type match + guard true**, **type match + guard false** và các component null.

## 6. Mẫu quyết định permission và state theo từng command

### 6.1. Create: quyền, ID hợp lệ, cuối cùng mới cho phép

```java
case Create(var taskId) when !actor.can(Permission.CREATE)
        -> Decision.deny("FORBIDDEN");
case Create(var taskId) when taskId == null || taskId.isBlank()
        -> Decision.deny("INVALID_INPUT");
case Create(var taskId) -> Decision.allow("CREATE");
```

Nhánh đầu loại actor thiếu quyền **trước khi** tiết lộ trạng thái hợp lệ của input. Nhánh thứ hai chặn ID không hợp lệ cho actor đã có quyền. Nhánh cuối không guard là đường còn lại: command đã qua hai điều kiện kiểm tra.

Nếu đảo nhánh Create không guard lên đầu, các nhánh Create có `when` phía sau sẽ bị che khuất. Compiler Java 21 có thể báo **dominated case label**, và dù không báo ở một biến thể nào đó, ý đồ xét quyền trước cũng bị phá.

### 6.2. Submit: chủ sở hữu hoặc người có quyền, task phải DRAFT

```java
case Submit(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Submit(var task) when !actor.can(Permission.SUBMIT)
        && !actor.id().equals(task.ownerId())
        -> Decision.deny("FORBIDDEN");
case Submit(var task) when task.state() != State.DRAFT
        -> Decision.deny("INVALID_STATE");
case Submit(var task) -> Decision.allow("SUBMIT");
```

Trong demo, **chủ sở hữu được submit ngay cả khi không có permission `SUBMIT`**; người không sở hữu cần permission này. Đó là một **quy tắc nghiệp vụ minh họa**, không phải chính sách mặc định của mọi tổ chức. Nếu dự án yêu cầu cả chủ sở hữu cũng phải có `SUBMIT`, bỏ vế kiểm tra chủ sở hữu khỏi điều kiện cho phép.

Nhánh kiểm tra null đứng trước vì điều kiện sở hữu cần đọc `task.ownerId()`. Sau khi task khác null, ta mới xét actor có permission hoặc là owner; sau khi được phép, mới xét `task.state() == DRAFT`.

**Chú ý bảo mật:** code chỉ dùng `task.ownerId()` từ object đã có trong bộ nhớ. Trong production, cần tải/đối chiếu owner từ kho dữ liệu đáng tin, gắn với tenant/scope, không chấp nhận một `Task` với `ownerId` do client tự ý dựng để cấp quyền.

### 6.3. Approve: quyền, dữ liệu, tách nhiệm vụ và trạng thái

```java
case Approve(var task) when !actor.can(Permission.APPROVE)
        -> Decision.deny("FORBIDDEN");
case Approve(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Approve(var task) when actor.id().equals(task.ownerId())
        -> Decision.deny("SELF_APPROVAL");
case Approve(var task) when task.state() != State.SUBMITTED
        -> Decision.deny("INVALID_STATE");
case Approve(var task) -> Decision.allow("APPROVE");
```

Lưu ý thứ tự:

1. Không có permission `APPROVE` → từ chối ngay.
2. Có quyền nhưng command không chứa task → input sai.
3. Người phê duyệt đồng thời là owner → `SELF_APPROVAL`.
4. Công việc chưa gửi duyệt hoặc đã duyệt/hủy → `INVALID_STATE`.
5. Khi tất cả điều kiện cấm đều không đúng → `ALLOW APPROVE`.

Đây là ví dụ về **separation of duties** (phân tách nhiệm vụ). Việc thêm `APPROVE` vào tập quyền của owner không vô hiệu hóa quy tắc cấm tự duyệt.

### 6.4. Cancel: quyền và nhóm trạng thái cho phép

```java
case Cancel(var task) when !actor.can(Permission.CANCEL)
        -> Decision.deny("FORBIDDEN");
case Cancel(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Cancel(var task) when task.state() == State.APPROVED
        || task.state() == State.CANCELLED
        -> Decision.deny("INVALID_STATE");
case Cancel(var task) -> Decision.allow("CANCEL");
```

Hệ kiểu `State` trong demo có đúng bốn trạng thái. Vì `APPROVED` và `CANCELLED` đã bị loại, trạng thái còn lại là `DRAFT` hoặc `SUBMITTED`, đều được hủy. Nếu trong tương lai thêm `ARCHIVED`, kiểu kiểm tra **liệt kê các trạng thái bị cấm** có thể vô tình cho phép hủy `ARCHIVED`.

Một cách **an toàn hơn khi thêm state** là viết guard cho **nhóm trạng thái được phép**:

```java
// Snippet thay thế cho hai nhánh state/allow của Cancel:
case Cancel(var task) when task.state() == State.DRAFT
        || task.state() == State.SUBMITTED
        -> Decision.allow("CANCEL");
case Cancel(var task) -> Decision.deny("INVALID_STATE");
```

Cách này *fail closed* với trạng thái mới. Chỉ dùng snippet sau các guard quyền và task null, vì nó đọc `task.state()`. Trong code hoàn chỉnh, bản đầu được giữ để minh họa rõ `when` cho nhánh từ chối; khi áp dụng vào production, hãy ưu tiên kiểm tra trực tiếp các trạng thái **được phép** hoặc một state machine riêng nếu tập trạng thái có thể phát triển.

## 7. Chương trình Java 21 hoàn chỉnh: 20 phép kiểm thử guard

Tạo tệp **`CommandGuardDemo.java`**:

```java
public class CommandGuardDemo {
    enum Permission { CREATE, SUBMIT, APPROVE, CANCEL }
    enum State { DRAFT, SUBMITTED, APPROVED, CANCELLED }

    record Actor(String id, java.util.Set<Permission> permissions) {
        Actor {
            java.util.Objects.requireNonNull(id, "actor id");
            permissions = java.util.Set.copyOf(
                java.util.Objects.requireNonNull(permissions, "permissions")
            );
        }
        boolean can(Permission permission) {
            return permissions.contains(permission);
        }
    }

    record Task(String id, String ownerId, State state) {
        Task {
            java.util.Objects.requireNonNull(id, "task id");
            java.util.Objects.requireNonNull(ownerId, "owner id");
            java.util.Objects.requireNonNull(state, "state");
        }
    }

    sealed interface Command permits Create, Submit, Approve, Cancel {}
    record Create(String taskId) implements Command {}
    record Submit(Task task) implements Command {}
    record Approve(Task task) implements Command {}
    record Cancel(Task task) implements Command {}

    record Decision(boolean allowed, String code) {
        static Decision allow(String code) {
            return new Decision(true, code);
        }
        static Decision deny(String code) {
            return new Decision(false, code);
        }
        public String toString() {
            return (allowed ? "ALLOW " : "DENY ") + code;
        }
    }

    static Decision decide(Actor actor, Command command) {
        if (actor == null) return Decision.deny("UNAUTHENTICATED");
        if (command == null) return Decision.deny("INVALID_COMMAND");

        return switch (command) {
            case Create(var taskId) when !actor.can(Permission.CREATE)
                -> Decision.deny("FORBIDDEN");
            case Create(var taskId) when taskId == null || taskId.isBlank()
                -> Decision.deny("INVALID_INPUT");
            case Create(var taskId) -> Decision.allow("CREATE");

            case Submit(var task) when task == null
                -> Decision.deny("INVALID_INPUT");
            case Submit(var task) when !actor.can(Permission.SUBMIT)
                    && !actor.id().equals(task.ownerId())
                -> Decision.deny("FORBIDDEN");
            case Submit(var task) when task.state() != State.DRAFT
                -> Decision.deny("INVALID_STATE");
            case Submit(var task) -> Decision.allow("SUBMIT");

            case Approve(var task) when !actor.can(Permission.APPROVE)
                -> Decision.deny("FORBIDDEN");
            case Approve(var task) when task == null
                -> Decision.deny("INVALID_INPUT");
            case Approve(var task) when actor.id().equals(task.ownerId())
                -> Decision.deny("SELF_APPROVAL");
            case Approve(var task) when task.state() != State.SUBMITTED
                -> Decision.deny("INVALID_STATE");
            case Approve(var task) -> Decision.allow("APPROVE");

            case Cancel(var task) when !actor.can(Permission.CANCEL)
                -> Decision.deny("FORBIDDEN");
            case Cancel(var task) when task == null
                -> Decision.deny("INVALID_INPUT");
            case Cancel(var task) when task.state() == State.APPROVED
                    || task.state() == State.CANCELLED
                -> Decision.deny("INVALID_STATE");
            case Cancel(var task) -> Decision.allow("CANCEL");
        };
    }

    static int checks;

    static void expect(String label, String expected, Decision decision) {
        String actual = decision.toString();
        if (!expected.equals(actual)) {
            throw new AssertionError(
                label + " expected=" + expected + " actual=" + actual
            );
        }
        checks++;
        System.out.println("PASS " + label + " => " + actual);
    }

    public static void main(String[] args) {
        Actor creator = new Actor("ann", java.util.Set.of(Permission.CREATE));
        Actor owner = new Actor("ann", java.util.Set.of());
        Actor submitter = new Actor("sam", java.util.Set.of(Permission.SUBMIT));
        Actor reviewer = new Actor("bob", java.util.Set.of(Permission.APPROVE));
        Actor approverOwner = new Actor("ann", java.util.Set.of(Permission.APPROVE));
        Actor operator = new Actor("ops", java.util.Set.of(Permission.CANCEL));
        Actor outsider = new Actor("eve", java.util.Set.of());

        Task draft = new Task("T1", "ann", State.DRAFT);
        Task submitted = new Task("T1", "ann", State.SUBMITTED);
        Task approved = new Task("T1", "ann", State.APPROVED);

        expect("create", "ALLOW CREATE", decide(creator, new Create("T1")));
        expect("create-no-permission", "DENY FORBIDDEN",
                decide(outsider, new Create("T1")));
        expect("create-blank", "DENY INVALID_INPUT",
                decide(creator, new Create(" ")));

        expect("submit-owner", "ALLOW SUBMIT", decide(owner, new Submit(draft)));
        expect("submit-permission", "ALLOW SUBMIT",
                decide(submitter, new Submit(draft)));
        expect("submit-forbidden", "DENY FORBIDDEN",
                decide(outsider, new Submit(draft)));
        expect("submit-wrong-state", "DENY INVALID_STATE",
                decide(owner, new Submit(submitted)));
        expect("submit-missing-task", "DENY INVALID_INPUT",
                decide(owner, new Submit(null)));

        expect("approve", "ALLOW APPROVE",
                decide(reviewer, new Approve(submitted)));
        expect("approve-forbidden", "DENY FORBIDDEN",
                decide(owner, new Approve(submitted)));
        expect("approve-self", "DENY SELF_APPROVAL",
                decide(approverOwner, new Approve(submitted)));
        expect("approve-wrong-state", "DENY INVALID_STATE",
                decide(reviewer, new Approve(draft)));
        expect("approve-missing-task", "DENY INVALID_INPUT",
                decide(reviewer, new Approve(null)));

        expect("cancel-draft", "ALLOW CANCEL",
                decide(operator, new Cancel(draft)));
        expect("cancel-submitted", "ALLOW CANCEL",
                decide(operator, new Cancel(submitted)));
        expect("cancel-approved", "DENY INVALID_STATE",
                decide(operator, new Cancel(approved)));
        expect("cancel-forbidden", "DENY FORBIDDEN",
                decide(outsider, new Cancel(draft)));
        expect("cancel-missing-task", "DENY INVALID_INPUT",
                decide(operator, new Cancel(null)));

        expect("no-actor", "DENY UNAUTHENTICATED",
                decide(null, new Create("T1")));
        expect("no-command", "DENY INVALID_COMMAND", decide(owner, null));

        System.out.println("checks=" + checks);
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 21 CommandGuardDemo.java
java CommandGuardDemo
```

**Stdout chính xác:**

```text
PASS create => ALLOW CREATE
PASS create-no-permission => DENY FORBIDDEN
PASS create-blank => DENY INVALID_INPUT
PASS submit-owner => ALLOW SUBMIT
PASS submit-permission => ALLOW SUBMIT
PASS submit-forbidden => DENY FORBIDDEN
PASS submit-wrong-state => DENY INVALID_STATE
PASS submit-missing-task => DENY INVALID_INPUT
PASS approve => ALLOW APPROVE
PASS approve-forbidden => DENY FORBIDDEN
PASS approve-self => DENY SELF_APPROVAL
PASS approve-wrong-state => DENY INVALID_STATE
PASS approve-missing-task => DENY INVALID_INPUT
PASS cancel-draft => ALLOW CANCEL
PASS cancel-submitted => ALLOW CANCEL
PASS cancel-approved => DENY INVALID_STATE
PASS cancel-forbidden => DENY FORBIDDEN
PASS cancel-missing-task => DENY INVALID_INPUT
PASS no-actor => DENY UNAUTHENTICATED
PASS no-command => DENY INVALID_COMMAND
checks=20
```

**Phân tích các nhóm kiểm tra:**

- **Create:** người có quyền được phép tạo với ID hợp lệ; người không có quyền nhận `FORBIDDEN`; ID trắng bị từ chối sau khi quyền được xác nhận.
- **Submit:** owner được submit dù không mang permission `SUBMIT` theo chính sách demo; người khác có permission vẫn được submit; outsider bị từ chối; task không ở `DRAFT` hoặc null không được submit.
- **Approve:** reviewer có quyền được duyệt `SUBMITTED`; không có quyền thì bị từ chối; owner có quyền nhưng tự duyệt vẫn bị cấm; `DRAFT` và task null đều không thể được duyệt.
- **Cancel:** người có permission `CANCEL` có thể hủy `DRAFT`/`SUBMITTED`; `APPROVED` và task null bị từ chối, outsider không được phép.
- **Pre-check:** null actor bị từ chối trước null command. Đây là **thứ tự ưu tiên có chủ đích** của chương trình.

Hàm `expect` chỉ in PASS khi chuỗi thực tế bằng expected; nếu khác, nó ném `AssertionError`. Dòng `checks=20` xác nhận **20 phép thử được định nghĩa trong demo** đã vượt qua, không chứng minh mọi trạng thái runtime, tổ hợp permission và cạnh tranh dữ liệu trong một hệ thống sản xuất đều đã được kiểm thử.

## 8. Vì sao switch exhaustive nhưng vẫn cần kiểm thử quyền?

Compiler Java 21 có thể biết `Command` chỉ cho phép các subtype `Create`, `Submit`, `Approve` và `Cancel`, vì hierarchy được `sealed`. Trong switch chính:

```java
case Approve(var task) when !actor.can(Permission.APPROVE) -> ...;
case Approve(var task) when task == null -> ...;
case Approve(var task) when actor.id().equals(task.ownerId()) -> ...;
case Approve(var task) when task.state() != State.SUBMITTED -> ...;
case Approve(var task) -> Decision.allow("APPROVE");
```

Nhánh `Approve(var task)` cuối cùng **không có guard**, nên nó bao phủ mọi trường hợp `Approve` còn lại. Tương tự ba subtype khác đều có case không guard cuối, khiến `switch expression` exhaustive.

Tuy nhiên, compiler chỉ đảm bảo có **đường chọn nhánh hợp lệ** cho những giá trị kiểu `Command`, **không** đảm bảo chính sách phân quyền đã đúng. Ví dụ:

- Nếu bạn vô tình đổi `!actor.can(APPROVE)` thành `actor.can(APPROVE)`, code vẫn biên dịch nhưng người được phép có thể bị từ chối và người không được phép có thể đi vào nhánh khác.
- Nếu bạn vô tình thay `state != SUBMITTED` thành `state == SUBMITTED`, compiler không nhận ra logic bị đảo.
- Nếu bạn bỏ guard `SELF_APPROVAL`, switch vẫn exhaustive nhưng vi phạm nghiệp vụ.

Do đó cần kiểm thử **positive/negative** cho từng quyền, trạng thái và quan hệ chủ sở hữu. `switch` làm quy tắc dễ đọc hơn chứ không thay thế automated tests hoặc threat modeling.

### 8.1. Khi thêm loại command mới

Giả sử bổ sung `Archive(Task task)` vào hierarchy. Nếu vẫn giữ switch không default và chưa có case Archive, compiler có thể báo switch expression không exhaustive sau khi biên dịch lại.

Đây là một lợi ích của `sealed + switch`: khi API thêm loại command mới, nhóm phát triển phải chủ động xem lại chính sách. Nếu dùng `default -> Decision.allow(...)` sẽ đặc biệt nguy hiểm: các command mới có thể được cấp quyền mặc định. Với quyết định bảo mật, **không bao giờ dùng nhánh tổng quát cho phép mọi command không nhận dạng được**.

Một nhánh `default -> Decision.deny("FORBIDDEN")` có thể phù hợp với một interface mở, nhưng trên hierarchy sealed đã đóng, việc bỏ default khiến compiler hỗ trợ phát hiện nhánh mới chưa được xử lý.

## 9. Guard quyền và guard trạng thái: thứ tự ảnh hưởng cả bảo mật

Cùng hai điều kiện, nhưng thứ tự có thể làm lộ thông tin:

```java
// Cấu trúc không nên dùng nếu người không có quyền
// vẫn có thể nhận thông tin chi tiết về trạng thái tài nguyên.
case Approve(var task) when task != null && task.state() != State.SUBMITTED
        -> Decision.deny("INVALID_STATE");
case Approve(var task) when !actor.can(Permission.APPROVE)
        -> Decision.deny("FORBIDDEN");
```

Trong ví dụ phản diện này, actor không có quyền có thể biết tài nguyên đang ở trạng thái nào qua mã trả về. Trong code chính, nhánh kiểm tra `APPROVE` đứng trước các nhánh đọc trạng thái. Đây chỉ là **một biện pháp giảm tiết lộ thông tin**, không bảo đảm chống mọi dạng information disclosure.

Cách sắp xếp an toàn trong trường hợp cần che trạng thái:

1. Xác định principal đáng tin và scope/tenant.
2. Kiểm tra permission cần thiết để truy cập tài nguyên.
3. Xác thực và tải tài nguyên (có thể gộp một số bước tùy chính sách để không xác nhận sự tồn tại).
4. Kiểm tra quyền theo từng tài nguyên: owner, tổ chức, vai trò, separation of duties.
5. Kiểm tra state transition.
6. Chỉ sau đó mới thực hiện tác vụ qua một thao tác ghi có điều kiện và ghi audit phù hợp.

Nếu command không chứa một `Task` hợp lệ, phải kiểm tra null trước khi dereference; thứ tự **đảm bảo an toàn null** cũng là điều kiện cần. Ví dụ `Submit(var task) when task == null` đứng trước điều kiện `task.ownerId()`.

**Thông điệp quan trọng:** thứ tự guard là một phần của hợp đồng nghiệp vụ và bảo mật; không nên đổi thứ tự chỉ để rút gọn code nếu chưa xác nhận tác động.

## 10. Dùng nested record pattern cho command khi nào?

Ngoài `Submit(var task)`, Java 21 cho phép phân rã sâu:

```java
// Snippet thay thế trong một switch trên Command,
// khi Actor actor đã xác thực và Task có ba component như ví dụ.
case Submit(Task(var taskId, var ownerId, var state))
        when actor.id().equals(ownerId) && state == State.DRAFT
        -> Decision.allow("SUBMIT");
```

Pattern `Submit(Task(...))` đồng thời đòi command thuộc loại Submit và component task là một `Task` **khác null**. Nó lấy `taskId`, `ownerId`, `state` ngay tại case.

**Khác biệt khi task null:** `Submit(Task(...))` **không khớp** nếu task null, còn `Submit(var task)` vẫn khớp và ràng buộc biến `task = null`. Nếu cần trả `INVALID_INPUT` riêng, hãy thêm case `Submit(var task) when task == null` ở vị trí phù hợp.

Không nhất thiết phải dùng nested record pattern ở mọi command. Trong code chính, `Submit(var task)` và `Approve(var task)` giữ nguyên object `Task` để minh họa rõ nhiều bước kiểm tra và thứ tự ưu tiên lỗi. Nested pattern phù hợp hơn khi code chủ yếu **đọc component** và không cần thông báo lỗi riêng cho từng cấp cấu trúc.

### Tránh áp dụng khi không đúng phiên bản

Cú pháp `record patterns` như `case Submit(Task(var id,...))` yêu cầu **Java 21** để dùng như tính năng chuẩn. Với Java 17, có thể dùng `instanceof Submit submit` rồi `submit.task()` và guard clauses trong phương thức. Pattern switch có preview ở một số bản cũ, nhưng không nên dùng preview như một giải pháp tương thích mặc định cho mã Java 17 production.

## 11. Bảo mật trong production: guard không phải một security boundary độc lập

Đây là phần quan trọng nhất khi chuyển demo thành code thật.

### 11.1. Actor phải được lấy từ nguồn xác thực đáng tin

Không làm thế này ở server:

```java
// PHẢN VÍ DỤ: không tin quyền do client tự gửi.
Actor actor = requestBody.actor();
Decision result = decide(actor, command);
```

Nếu client kiểm soát `actor.permissions`, họ có thể tự thêm `APPROVE` hoặc `CANCEL`. Khi đó `when actor.can(...)` chạy đúng logic Java nhưng quyết định **không an toàn** vì nguồn dữ liệu quyền không đáng tin.

Thay vào đó, actor phải được dựng/giải quyết từ principal đã xác thực và chính sách quyền ở phía server. Dữ liệu về owner, tenant, trạng thái cũng phải đến từ nguồn đáng tin; không dựa vào một `Task` do caller tự điền `ownerId`.

### 11.2. Quyền tổng quát chưa đủ để xử lý tài nguyên cụ thể

Permission `APPROVE` chưa có nghĩa được duyệt mọi task trong toàn hệ thống. Tùy domain, cần kiểm tra:

- Tài nguyên có thuộc tenant/tổ chức mà actor được phép truy cập không?
- Actor có role/quyền hiệu lực trên workflow hoặc nhóm đó không?
- Có quy tắc maker–checker hoặc separation of duties nào không?
- Có lệnh cấm do trạng thái đóng băng, xung đột quyền, hạn mức hay giai đoạn phê duyệt không?

Ví dụ minh họa mô hình chung:

```java
// Snippet kiến trúc, các collaborator do ứng dụng cung cấp.
Task task = taskRepository.loadAuthorizedView(taskId, trustedPrincipal);
PermissionSet permissions = policyService.effectivePermissions(trustedPrincipal, task);
Decision decision = commandPolicy.decide(trustedPrincipal, permissions, task, command);
```

Các tên `taskRepository`, `PermissionSet` và `commandPolicy` là thành phần giả định của ứng dụng; đây **không phải** Java SDK sẵn có và **không phải đoạn chạy độc lập**. Ý chính: phải giải quyết đúng dữ liệu đáng tin và phạm vi quyền **trước khi** áp dụng biểu thức guard.

### 11.3. Không để guard tự gây side effect

Một biểu thức `when` lý tưởng nên đơn giản, dễ dự đoán và **không thay đổi dữ liệu**:

```java
case Approve(var task) when actor.can(Permission.APPROVE)
        && task != null && task.state() == State.SUBMITTED
        -> Decision.allow("APPROVE");
```

Không nên dùng guard kiểu “thử cập nhật DB rồi trả boolean” hoặc gọi dịch vụ từ xa có side effect để quyết định case. Guard chỉ nên **kiểm tra**, còn việc thực thi nên diễn ra ở một bước riêng, có transaction hoặc điều kiện ghi thích hợp.

Khi guard dùng nhiều hàm có độ trễ hoặc có thể ném lỗi, việc Java đánh giá case theo thứ tự có thể làm việc debug và kiểm thử phức tạp. Trích logic thành phương thức thuần hoặc tập trung policy thường dễ bảo trì hơn.

### 11.4. Không để decision và mutation bị lệch thời điểm (TOCTOU)

Giả sử:

1. `decide(actor, new Approve(task))` thấy task ở `SUBMITTED` và trả `ALLOW APPROVE`.
2. Luồng khác chuyển task sang `CANCELLED`.
3. Luồng đầu ghi `APPROVED` mà không kiểm tra lại state.

Đó là lỗi **time-of-check to time-of-use**. Một quyết định được tính từ bản snapshot cũ **không đảm bảo state vẫn đúng khi ghi**.

Giải pháp ở tầng lưu trữ/transaction:

- Đọc task trong phạm vi transaction thích hợp hoặc dùng optimistic locking với version.
- Thực hiện update có điều kiện: chỉ chuyển state nếu ID, tenant/ownership, state/version hiện tại và quyền có hiệu lực còn phù hợp.
- Kiểm tra số bản ghi thực sự được cập nhật; nếu không đúng kỳ vọng, báo conflict/retry theo hợp đồng.
- Ghi audit/event cùng giao dịch khi cần; tránh công bố thành công trước khi commit.

Một mẫu SQL **minh họa khái niệm**, không phải câu SQL dành cho mọi schema:

```sql
UPDATE tasks
SET state = 'APPROVED', version = version + 1
WHERE id = :taskId
  AND tenant_id = :tenantId
  AND state = 'SUBMITTED'
  AND version = :expectedVersion;
```

Dù câu update kiểm tra state/version, **ủy quyền actor vẫn phải được kiểm tra ở server**, vì câu SQL này chỉ thể hiện một phần business invariant, không phải toàn bộ chính sách phân quyền. Nếu update trả 0 dòng, có thể do tài nguyên không tồn tại, state/version thay đổi hoặc scope không phù hợp; ứng dụng phải quyết định cách trả lỗi mà không tiết lộ thông tin quá mức.

### 11.5. Thông báo lỗi và audit

Trong demo, `Decision.code` phân biệt `FORBIDDEN`, `INVALID_STATE`, `SELF_APPROVAL` để phục vụ học tập. Trong production, response công khai có thể cần **gộp các lỗi nhạy cảm** để tránh xác nhận tài nguyên tồn tại hoặc trạng thái nội bộ. Audit có thể chứa thông tin chi tiết hơn, nhưng phải được bảo vệ, tránh log token, thông tin nhạy cảm hoặc dữ liệu người dùng không cần thiết.

## 12. Kiểm thử guard: xây dựng ma trận quyền × trạng thái

Một lỗi dễ gặp là chỉ test trường hợp thành công. Với policy command, đường **DENY** đôi khi quan trọng hơn đường ALLOW.

Bảng dữ liệu kiểm thử gợi ý:

| Command | Actor/permission | State | Mong đợi |
| --- | --- | --- | --- |
| Create | Có CREATE | ID hợp lệ | `ALLOW CREATE` |
| Create | Không CREATE | ID hợp lệ | `DENY FORBIDDEN` |
| Create | Có CREATE | ID trắng | `DENY INVALID_INPUT` |
| Submit | Là owner | DRAFT | `ALLOW SUBMIT` |
| Submit | Có SUBMIT, không phải owner | DRAFT | `ALLOW SUBMIT` |
| Submit | Không SUBMIT, không owner | DRAFT | `DENY FORBIDDEN` |
| Submit | Là owner | SUBMITTED | `DENY INVALID_STATE` |
| Submit | Task null | — | `DENY INVALID_INPUT` |
| Approve | Có APPROVE, khác owner | SUBMITTED | `ALLOW APPROVE` |
| Approve | Không APPROVE | SUBMITTED | `DENY FORBIDDEN` |
| Approve | Có APPROVE nhưng là owner | SUBMITTED | `DENY SELF_APPROVAL` |
| Approve | Có APPROVE, khác owner | DRAFT | `DENY INVALID_STATE` |
| Cancel | Có CANCEL | DRAFT / SUBMITTED | `ALLOW CANCEL` |
| Cancel | Có CANCEL | APPROVED | `DENY INVALID_STATE` |
| Cancel | Không CANCEL | DRAFT | `DENY FORBIDDEN` |
| Bất kỳ | Actor null | — | `DENY UNAUTHENTICATED` |
| Null command | Actor hợp lệ | — | `DENY INVALID_COMMAND` |

Cần thêm kiểm thử ở những giao điểm có nhiều lỗi cùng xảy ra để xác nhận thứ tự ưu tiên. Ví dụ, `Approve` không có permission nhưng task đang DRAFT phải trả `FORBIDDEN` theo code hiện tại, không tiết lộ `INVALID_STATE`. Một owner có quyền APPROVE nhưng đang tự duyệt task DRAFT sẽ nhận `SELF_APPROVAL` trước `INVALID_STATE`. Nếu nghiệp vụ muốn ưu tiên khác, hãy định nghĩa lại và cập nhật tests, thay vì thay thứ tự case ngẫu nhiên.

### Gợi ý JUnit Jupiter

Trong project có dependency JUnit Jupiter, bạn có thể kiểm tra policy bằng:

```java
// Snippet JUnit 5, đặt trong cùng package với CommandGuardDemo.
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CommandGuardDemoTest {
    @Test
    void unauthorizedActorCannotApproveSubmittedTask() {
        var actor = new CommandGuardDemo.Actor(
            "eve", java.util.Set.of()
        );
        var task = new CommandGuardDemo.Task(
            "T1", "ann", CommandGuardDemo.State.SUBMITTED
        );
        var result = CommandGuardDemo.decide(
            actor, new CommandGuardDemo.Approve(task)
        );
        assertEquals("DENY FORBIDDEN", result.toString());
    }

    @Test
    void approverCannotApproveOwnTask() {
        var actor = new CommandGuardDemo.Actor(
            "ann", java.util.Set.of(CommandGuardDemo.Permission.APPROVE)
        );
        var task = new CommandGuardDemo.Task(
            "T1", "ann", CommandGuardDemo.State.SUBMITTED
        );
        assertEquals(
            "DENY SELF_APPROVAL",
            CommandGuardDemo.decide(
                actor, new CommandGuardDemo.Approve(task)
            ).toString()
        );
    }
}
```

Đây là **mẫu test sử dụng JUnit 5**, yêu cầu thêm dependency/test runner và cùng package để truy cập các record/method package-private; nó không thuộc tệp chương trình độc lập ở mục 7. Trong ứng dụng production, nên test bằng API chính thức của policy service thay vì dựa vào kiểu visibility của demo.

Ngoài unit tests, cần **integration tests** cho việc tải actor/resource đáng tin, kiểm tra tenant, persistence transaction, idempotency và cập nhật state khi có hai request cạnh tranh.

## 13. Những lỗi thường gặp với guard quyền/trạng thái

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ dùng `case Approve(var task) -> allow(...)` | Ai gửi command Approve cũng được phép. | Thêm guard quyền và nhánh từ chối. |
| Đặt case không guard ở trước case có `when` cùng loại | Case cụ thể bị che, có thể lỗi compile-time. | Đặt case hẹp trước case tổng quát. |
| Dùng `task.state()` khi task null | `NullPointerException`. | Xử lý null trước khi đọc component hoặc dùng nested pattern có fallback rõ. |
| Xác thực actor bằng dữ liệu từ request body | Client có thể tự gán permission. | Lấy actor từ security context đã xác minh, nguồn quyền đáng tin. |
| Tin `ownerId` do client gửi | Cho phép giả mạo sở hữu tài nguyên. | Tải owner/tenant từ database có kiểm tra scope. |
| Chỉ kiểm tra permission, bỏ qua state | Duyệt/hủy task ở trạng thái không hợp lệ. | Tách guard trạng thái sau kiểm tra quyền. |
| Chỉ kiểm tra state, bỏ qua permission | Người không có quyền vẫn thực thi command. | Kiểm tra actor và quyền trước thao tác nhạy cảm. |
| Không test `when` false | Bỏ sót đường DENY. | Test cả trường hợp được phép và bị từ chối. |
| Thêm `default -> allow(...)` | Command mới không nhận diện có thể được cấp quyền. | Fail closed; với sealed hierarchy, liệt kê case đầy đủ. |
| Guard gọi DB hoặc thay đổi state | Khó dự đoán thứ tự, nguy cơ side effect trước khi authorize. | Dùng guard thuần, tách bước thực thi. |
| Kiểm tra trước rồi update không có điều kiện | Race condition/TOCTOU khi state hoặc quyền đổi. | Transaction, optimistic locking hoặc conditional update. |
| Dùng tập trạng thái bị cấm thay vì tập trạng thái được phép | State mới có thể tự động lọt qua. | Với thao tác nhạy cảm, ưu tiên allowlist state. |
| Trả lỗi chi tiết cho actor không có quyền | Có thể tiết lộ tài nguyên/trạng thái. | Quyết định mức thông báo lỗi công khai theo threat model. |
| Coi `ALLOW` đồng nghĩa đã lưu thành công | Bỏ qua lỗi persistence và transaction. | Xem Decision là bước xét điều kiện; chỉ báo thành công sau khi commit. |
| Xem `switch` exhaustive là đủ bảo mật | Compiler chỉ kiểm tra loại command được bao phủ. | Test policy, xác thực principal và kiểm tra dữ liệu thực tế. |

## 14. Bài tập: mở rộng command policy

### Bài A — Thêm Reopen cho task đã CANCELLED

Mở rộng:

```java
// Snippet khai báo thêm trong class có Command/Task/State.
record Reopen(Task task) implements Command {}
```

Yêu cầu:

- Actor có permission mới `REOPEN`.
- Chỉ cho phép khi task `CANCELLED`.
- Task null phải bị từ chối.
- Không thêm `default -> allow(...)`.

Gợi ý thứ tự case:

```java
case Reopen(var task) when !actor.can(Permission.REOPEN)
        -> Decision.deny("FORBIDDEN");
case Reopen(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Reopen(var task) when task.state() != State.CANCELLED
        -> Decision.deny("INVALID_STATE");
case Reopen(var task) -> Decision.allow("REOPEN");
```

Đây là **snippet mở rộng**, chưa chạy độc lập: phải bổ sung `REOPEN` vào enum Permission, thêm `Reopen` vào `permits` của Command và thêm các case trên trong switch. Compiler Java 21 sẽ giúp phát hiện thiếu nhánh Reopen nếu hierarchy được mở rộng mà switch không có default.

### Bài B — Thiết kế guard an toàn khi có state mới

Nếu bổ sung `ARCHIVED` vào enum State, hãy xem nhánh Cancel trong demo: nó chỉ cấm APPROVED/CANCELLED, nên `ARCHIVED` **vô tình được phép**.

Viết lại Cancel theo allowlist:

```java
case Cancel(var task) when !actor.can(Permission.CANCEL)
        -> Decision.deny("FORBIDDEN");
case Cancel(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Cancel(var task) when task.state() == State.DRAFT
        || task.state() == State.SUBMITTED
        -> Decision.allow("CANCEL");
case Cancel(var task) -> Decision.deny("INVALID_STATE");
```

Test `Cancel(ARCHIVED)` nhận `DENY INVALID_STATE`. Đây là một kỹ thuật **fail-closed đối với trạng thái mới** mà không cần ghi tên mọi state bị từ chối.

### Bài C — Phân tích ưu tiên lỗi

Một actor vừa **không có APPPROVE permission** vừa muốn approve một task đang DRAFT. Theo code demo, kết quả là gì?

**Đáp án:** `DENY FORBIDDEN` vì guard `!actor.can(APPROVE)` đứng trước việc kiểm tra trạng thái. Đó là hành vi có chủ đích để tránh trả thông tin về state cho người thiếu quyền.

Nếu actor có permission APPROVE nhưng đồng thời là owner của task, kết quả là `DENY SELF_APPROVAL` trước khi kiểm tra `state != SUBMITTED`. Khi đổi thứ tự, cần cập nhật đặc tả và regression tests.

## 15. Checklist khi đưa guard vào hệ thống thật

1. **Xác định trust boundary:** Actor được xác thực ở phía server; quyền và chủ sở hữu không đến trực tiếp từ field client có thể sửa.
2. **Định nghĩa policy bằng bảng:** Với từng command, ghi quyền, trạng thái, quan hệ sở hữu, kết quả ALLOW/DENY và mã lỗi.
3. **Đóng tập command nếu phù hợp:** Dùng `sealed interface` và record để compiler giúp phát hiện subtype mới chưa được xử lý.
4. **Đặt guard hẹp trước case rộng:** Nhánh `when` trước nhánh cùng type không guard; kiểm tra null trước khi dereference.
5. **Ưu tiên kiểm tra quyền trước khi tiết lộ state:** Thiết kế thông báo lỗi phù hợp với threat model và yêu cầu chống dò tìm tài nguyên.
6. **Cân nhắc allowlist state:** Chỉ cho phép các chuyển trạng thái đã xác định; state mới mặc định bị từ chối nếu policy chưa cập nhật.
7. **Giữ guard dễ đánh giá:** Tránh side effects/I/O trong `when`, tách kiểm tra khỏi thực thi.
8. **Xác minh lại lúc ghi:** Bảo đảm state, scope/tenant và permission có hiệu lực khi thực hiện transaction; phòng TOCTOU.
9. **Kiểm thử ma trận:** Ít nhất mỗi command có ALLOW, thiếu quyền, sai state, null và quy tắc owner đặc thù nếu có.
10. **Audit và phản hồi đúng mức:** Lưu mã quyết định cần thiết để điều tra, bảo vệ log, không trả dữ liệu trạng thái nhạy cảm cho actor thiếu quyền.
11. **Đảm bảo phiên bản:** Record patterns/guard `when` ở switch dùng Java 21; project Java 17 cần cách viết tương thích hơn.
12. **Không nhầm Decision với mutation:** Chỉ trả thành công thực sự sau khi lệnh đã được thực thi/commit.

## 16. Tổng kết

**Guard `when` trong pattern switch** rất phù hợp với một command processor có **nhiều loại lệnh** và các điều kiện quyền/trạng thái khác nhau. Nhờ `case Create(...)`, `Submit(...)`, `Approve(...)`, `Cancel(...)`, logic chọn loại command nằm trên một cấu trúc rõ ràng; các guard diễn đạt chính sách, và nhánh không guard cuối cùng tạo fallback cho mỗi kiểu.

Tuy vậy, **mã Java biên dịch được không đồng nghĩa bảo mật đúng**. Hệ thống vẫn phải dùng actor và tài nguyên đáng tin, xử lý null, ưu tiên DENY khi chưa đủ quyền, chống tự phê duyệt và race condition khi cập nhật state. Hãy kiểm thử cả **ALLOW lẫn DENY** và coi switch là **nơi diễn đạt policy**, không phải bằng chứng duy nhất của việc ủy quyền thành công.

**Tài liệu tham khảo:**

- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
