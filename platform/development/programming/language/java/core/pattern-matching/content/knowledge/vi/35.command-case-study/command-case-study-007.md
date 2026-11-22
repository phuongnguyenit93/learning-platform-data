# Thêm command mới an toàn

## 1. Bài toán: thêm lệnh mà không phá hành vi cũ

Trong một ứng dụng quản lý công việc, **command** biểu diễn một yêu cầu thực hiện hành động: tạo công việc, đổi tên, đánh dấu hoàn thành hoặc lưu trữ. Khác với một event mô tả điều **đã xảy ra**, command diễn tả điều **được yêu cầu xảy ra**; nó có thể bị từ chối vì thiếu quyền, dữ liệu không hợp lệ hoặc trạng thái hiện tại không cho phép.

Giả sử phiên bản đầu tiên hỗ trợ:

- `CreateTask`: tạo công việc.
- `RenameTask`: đổi tên công việc.
- `CompleteTask`: đánh dấu công việc hoàn thành.

Phiên bản tiếp theo cần thêm `ArchiveTask`, nhưng việc lưu trữ chỉ được phép với vai trò **ADMIN** và không được xử lý công việc đã lưu trữ. Đây không chỉ là việc thêm một record:

1. **Định nghĩa lệnh mới** với cấu trúc và validation rõ ràng.
2. **Mở rộng tập lệnh được phép** trong mô hình domain.
3. **Buộc nơi dispatch xử lý lệnh mới**, không âm thầm rơi vào `default`.
4. **Kiểm tra quyền trước khi thay đổi trạng thái**.
5. **Giữ các quy tắc chuyển trạng thái** và không thực hiện một nửa công việc rồi mới phát hiện lỗi.
6. **Kiểm thử lệnh mới cùng những lệnh cũ**, bao gồm dữ liệu sai, không có quyền và lặp yêu cầu.
7. **Đánh giá tương thích** với API, dữ liệu đã lưu, message queue và các module được phát hành độc lập.

Từ **Java 21**, `sealed interface` kết hợp **record patterns** và **pattern matching for `switch`** cung cấp một cách diễn đạt những yêu cầu trên rõ ràng, đặc biệt khi tập command được quản lý trong một module.

**Nguyên tắc trung tâm:** Thêm command an toàn không có nghĩa chỉ làm cho chương trình biên dịch. Nó có nghĩa là **command mới được nhận diện đúng, kiểm tra đúng quyền và dữ liệu, thay đổi trạng thái đúng hợp đồng, đồng thời không làm các command cũ đổi nghĩa**.

## 2. Mô hình command bằng sealed interface

### Phiên bản ban đầu

```java
sealed interface TaskCommand
        permits CreateTask, RenameTask, CompleteTask {}

record CreateTask(String id, String title)
        implements TaskCommand {}

record RenameTask(String id, String newTitle)
        implements TaskCommand {}

record CompleteTask(String id)
        implements TaskCommand {}
```

Đây là ví dụ khai báo để giải thích thiết kế; **chưa có validation**. Mỗi command là một **record** chứa dữ liệu cần thiết cho một ý định nghiệp vụ.

Dùng `sealed interface` có các lợi ích:

- Tập subtype **trực tiếp** được phép được định nghĩa rõ tại `permits`.
- Record là `final`, nên trong mô hình này các nhánh command không bị kế thừa tiếp.
- Nơi tiêu thụ command có thể dùng `switch expression` và để compiler kiểm tra **exhaustiveness**.
- Một module không thể tự ý thêm implementation trực tiếp của `TaskCommand` nếu chưa thuộc tập được cho phép.

Với **named module**, subtype trực tiếp được `permits` phải nằm trong cùng module với sealed type; với **unnamed module**, chúng phải cùng package. Các khai báo lồng trong lớp của ví dụ chạy đầy đủ ở phần sau đáp ứng ràng buộc tổ chức này.

### Thêm ArchiveTask

Khi có yêu cầu lưu trữ, ta cập nhật hợp đồng:

```java
sealed interface TaskCommand
        permits CreateTask, RenameTask, CompleteTask, ArchiveTask {}

record ArchiveTask(String id) implements TaskCommand {}
```

Đây là **hình thức sau khi mở rộng**; không đặt cả hai khai báo `TaskCommand` ở cùng một file. Record `ArchiveTask` chỉ cần `id` vì ý định của nó là chuyển một công việc đã tồn tại sang trạng thái lưu trữ.

Điểm an toàn không nằm ở câu lệnh `permits` đơn lẻ. **Mọi nơi quyết định cách thực thi command** cũng cần được đánh giá: command dispatcher, kiểm tra quyền, validation, audit, test, serialization và các consumer của API.

## 3. Exhaustiveness: để compiler giúp phát hiện nơi chưa xử lý command mới

Giả sử handler của phiên bản đầu là:

```java
static String execute(TaskCommand command) {
    return switch (command) {
        case CreateTask create -> createTask(create);
        case RenameTask rename -> renameTask(rename);
        case CompleteTask complete -> completeTask(complete);
        case null -> throw new IllegalArgumentException(
                "command must not be null");
    };
}
```

Đoạn trên **minh họa**: các hàm `createTask`, `renameTask`, `completeTask` chưa được khai báo trong snippet này. Nó mô tả một `switch expression` trên hierarchy đóng.

Khi `TaskCommand` chỉ `permits` ba subtype cũ, compiler Java 21 có đủ thông tin để kiểm tra các nhánh không-null. Nhưng sau khi thêm `ArchiveTask` vào `permits`, bản handler trên **không còn bao phủ mọi subtype** và có thể bị báo lỗi không exhaustive khi biên dịch lại.

Đây là một tín hiệu hữu ích: đội ngũ phải quyết định `ArchiveTask` được xử lý thế nào, thay vì để runtime tùy ý thực hiện một fallback chung.

### Anti-pattern: thêm default cho “hết lỗi compiler”

```java
return switch (command) {
    case CreateTask create -> createTask(create);
    case RenameTask rename -> renameTask(rename);
    case CompleteTask complete -> completeTask(complete);
    case null -> throw new IllegalArgumentException("Missing command");
    default -> "IGNORED";
};
```

Đoạn này cũng chỉ là minh họa với các hàm chưa định nghĩa. Một `default -> "IGNORED"` khiến `ArchiveTask` không tạo ra hành vi lưu trữ; nếu người gọi hiểu `"IGNORED"` như một kết quả thành công, lỗi càng khó phát hiện.

**Không phải mọi `default` đều xấu**: với command extension point **mở** hoặc một gateway phải từ chối loại chưa hỗ trợ, `default -> throw new UnsupportedOperationException(...)` có thể là chính sách đúng. Nhưng trong một sealed hierarchy được dùng để mô tả tập command hữu hạn, thường tốt hơn khi **liệt kê các case nghiệp vụ** và không che mất tín hiệu thiếu xử lý.

## 4. Record pattern và dispatcher sau khi thêm command

Từ Java 21, một handler có thể phân rã các record trực tiếp trong `case`:

```java
static String execute(TaskCommand command, Role role) {
    if (role == null) {
        throw new IllegalArgumentException("role must not be null");
    }

    return switch (command) {
        case CreateTask(String id, String title) ->
                create(id, title);

        case RenameTask(String id, String newTitle) ->
                rename(id, newTitle);

        case CompleteTask(String id) ->
                complete(id);

        case ArchiveTask(String id) when role != Role.ADMIN ->
                throw new SecurityException(
                        "Only ADMIN may archive");

        case ArchiveTask(String id) ->
                archive(id);

        case null ->
                throw new IllegalArgumentException(
                        "command must not be null");
    };
}
```

Đây là **đoạn minh họa trong ngữ cảnh domain**: `Role` và bốn hàm thao tác sẽ được định nghĩa trong chương trình độc lập ở phần 9.

Điểm đáng chú ý:

- `CreateTask(String id, String title)` là **record pattern**: kiểm tra subtype và lấy giá trị component, không cần `(CreateTask) command`.
- `ArchiveTask(String id) when role != Role.ADMIN` là **guarded pattern**. `when` chỉ được xét sau khi record pattern khớp.
- Khi người dùng không có quyền, nhánh guard ném `SecurityException` **trước khi gọi `archive(id)`**, nên không có thao tác lưu trữ ở nhánh đó.
- `case ArchiveTask(String id)` không guard phải đứng **sau** nhánh kiểm tra quyền, để xử lý các trường hợp được phép.
- `case null` quyết định rõ chính sách command null. Nó **không đồng nghĩa** với `default`.
- Vì mọi subtype của `TaskCommand` đều được bao phủ, biểu thức không cần nhánh `default`.

**Cẩn thận với nguồn của `role`:** trong ứng dụng thực tế, quyền phải được xác định từ **danh tính đã xác thực ở server hoặc security context đáng tin**, không lấy một chuỗi `"ADMIN"` do client tự gửi rồi tin ngay. Tham số `role` trong case study chỉ là dữ liệu đã được xác định ở tầng gọi, dùng để minh họa logic phân quyền.

### Khi nào dùng type pattern thay cho record pattern?

Nếu một command có nhiều component hoặc cần chuyển nguyên command xuống service, type pattern có thể dễ đọc hơn:

```java
case CreateTask create -> createService.execute(create);
```

Đây là snippet ý tưởng, giả định có `createService`. Không bắt buộc mọi case đều phải phân rã mọi component. Với record pattern, hãy dùng khi việc thấy trực tiếp các trường `id`, `title` làm chính sách rõ ràng hơn.

## 5. Validate command ngay từ điểm vào

Không nên chờ đến khi map lưu công việc phát sinh lỗi mới nhận ra `id` rỗng hoặc `title` null.

Record có thể dùng **compact constructor** để kiểm tra các trường:

```java
record CreateTask(String id, String title)
        implements TaskCommand {
    CreateTask {
        requireNonBlank(id, "id");
        requireNonBlank(title, "title");
    }
}
```

Snippet này giả định hàm `requireNonBlank` được định nghĩa ở cùng phạm vi (ví dụ là static method của lớp chứa record), giống chương trình đầy đủ phía dưới.

Hàm kiểm tra:

```java
static void requireNonBlank(String text, String field) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(
                field + " must not be blank");
    }
}
```

Làm tương tự với `RenameTask`, `CompleteTask` và `ArchiveTask` để bảo đảm những command được tạo bình thường có `id` khác null và không chỉ là khoảng trắng.

**Phân biệt hai lớp validation:**

1. **Validation cú pháp/cấu trúc tại command:** `id` không được blank, `title` phải có nội dung, dữ liệu nằm trong phạm vi cho phép.
2. **Validation trạng thái tại handler:** công việc đã tồn tại chưa, đã lưu trữ chưa, đã hoàn thành chưa, người gọi có quyền không.

Không nên đặt quy tắc “ID phải tồn tại trong cơ sở dữ liệu” vào constructor record nếu quy tắc đó phụ thuộc trạng thái bên ngoài. Constructor nên xác thực những bất biến nội tại của dữ liệu lệnh; việc kiểm tra trạng thái nghiệp vụ cần tiến hành trong quá trình thực thi có kiểm soát.

### Record pattern và component null

`case CreateTask(String id, String title)` dùng các **type pattern con `String`**. Trong Java 21, component `null` không khớp type pattern `String`. Trong chương trình bên dưới, compact constructor chủ động từ chối null, nên những command được tạo hợp lệ không có component null.

Nếu nhận dữ liệu từ kênh không đáng tin, nên validate khi decode/deserialize, không giả định rằng pattern matching sẽ tự sửa mọi component sai. Trong mô hình khác cho phép null, có thể dùng `var` và kiểm tra null tường minh hoặc thêm nhánh subtype rộng hơn; không nên để command hợp lệ theo kiểu nhưng bị bỏ qua vì record pattern không khớp component.

## 6. An toàn nghiệp vụ: quyền, trạng thái và mutation

Giả sử dữ liệu công việc gồm:

```java
record Task(
        String id,
        String title,
        boolean completed,
        boolean archived) {}
```

Quy tắc trong case study:

- **CreateTask:** chỉ tạo khi `id` chưa tồn tại.
- **RenameTask:** chỉ đổi tên công việc tồn tại và chưa lưu trữ.
- **CompleteTask:** chỉ hoàn thành công việc tồn tại, chưa lưu trữ và chưa hoàn thành.
- **ArchiveTask:** chỉ ADMIN được gọi; công việc phải tồn tại và chưa lưu trữ. Công việc đã hoàn thành vẫn có thể lưu trữ.

Các quy tắc này là **hợp đồng minh họa**. Ứng dụng khác có thể cho phép hoàn thành lặp lại như thao tác idempotent, hoặc chỉ cho phép archive sau khi hoàn thành; khi đó cần định nghĩa và test hợp đồng khác, không phải đổi cú pháp `switch` là đủ.

### Kiểm tra trước khi ghi trạng thái

Một thao tác đổi tên cần có thứ tự:

1. Tìm công việc bằng `id`.
2. Từ chối nếu không tồn tại hoặc đã archived.
3. Tạo phiên bản `Task` mới với tiêu đề cập nhật.
4. Ghi lại trạng thái bằng một thao tác có kiểm soát.

Không viết:

```java
// Ý tưởng nguy hiểm: cập nhật một phần rồi mới kiểm tra.
store.put(id, new Task(id, newTitle, false, false));
if (!isAllowedToRename(id)) {
    throw new SecurityException("Denied");
}
```

Các tên `store` và `isAllowedToRename` là minh họa. Lúc exception xảy ra, dữ liệu đã bị thay đổi; **ném lỗi không tự rollback một thay đổi đã làm trong bộ nhớ**.

Đối với hệ thống sử dụng database, quá trình kiểm tra và ghi phải xét **giao dịch, isolation hoặc optimistic locking** để không bị race condition giữa đọc và cập nhật. Một `HashMap` hoặc `LinkedHashMap` dùng trong demo không tạo được các bảo đảm ấy khi có nhiều luồng hoặc nhiều server.

### Quyền kiểm tra trước side effect

Trong handler, case có guard quyền đứng trước case `ArchiveTask` thực thi. Đó là một cấu trúc giúp người đọc thấy quyền bắt buộc đối với lệnh mới. Trong ứng dụng thực tế nên đặt kiểm soát quyền ở ranh giới tin cậy và có thể kiểm tra lặp lại ở application service khi cần, thay vì dựa vào một giao diện người dùng ẩn nút archive.

### Lỗi phải rõ nghĩa

Phân biệt:

- `IllegalArgumentException`: command không hợp lệ hoặc tham chiếu ID không tồn tại theo hợp đồng ví dụ.
- `IllegalStateException`: công việc tồn tại nhưng trạng thái không cho phép thao tác.
- `SecurityException`: người gọi không được phép archive.

Có thể thay những exception chung bằng **domain error/result type** nếu API cần trả lỗi có mã ổn định hoặc hỗ trợ client tự phục hồi. Không có lý do để mọi lỗi bị biến thành `"OK"` hoặc `default -> ""`.

## 7. Không nhầm tính đầy đủ ở compiler với an toàn runtime

Với sealed hierarchy, `switch expression` không có `default` giúp phát hiện khi thêm subtype nhưng chưa bổ sung case **trong những module được biên dịch lại**.

Tuy nhiên:

- Compiler không biết mọi quy tắc quyền và trạng thái nằm ngoài kiểu dữ liệu.
- Sealed không tự bảo đảm ID tồn tại, title có nghĩa, hay người gọi được xác thực.
- Một command mới có thể được tạo đúng cú pháp nhưng thực hiện sai side effect nếu handler viết thiếu transaction.
- Nếu các module được build/phát hành lệch phiên bản, một switch cũ đã biên dịch có thể gặp subtype mới lúc runtime; cần quản lý tương thích và có thể gặp `MatchException` với hierarchy không còn khớp giả định biên dịch.
- Khi gửi command qua mạng, payload cũng có thể có version/schema khác nhau; Java type system của một module không tự bảo đảm hệ thống phân tán đồng bộ phiên bản.

**Thông điệp:** exhaustiveness là một **hàng rào an toàn bổ sung**, không phải sự thay thế cho validation, authorization, test, cơ chế nhất quán dữ liệu và quy trình phát hành.

## 8. Lộ trình thêm command mới theo từng bước

Một thay đổi thực tế có thể được review theo trình tự sau:

### Bước 1 — Chốt ý nghĩa command

Với `ArchiveTask`, định nghĩa: ai được archive, khi nào, mục đích là gì, có đảo ngược được không, archive lặp lại trả gì, và kết quả lỗi nào được công bố.

Tránh định nghĩa mơ hồ kiểu “archive là update status” vì nó không nói rõ các ràng buộc quan trọng.

### Bước 2 — Thêm record với dữ liệu tối thiểu

`record ArchiveTask(String id) implements TaskCommand` biểu diễn một hành động rõ. Nếu nghiệp vụ cần thêm `reason` hoặc `requestedAt`, cân nhắc dữ liệu đó có cần hiện diện ở command ngay từ đầu không. Không để handler lấy những thông tin quan trọng từ biến global thiếu kiểm soát.

### Bước 3 — Cập nhật sealed permits

Thêm subtype trực tiếp vào `TaskCommand` và bảo đảm nó nằm trong module/package phù hợp. Vì record là final nên không phải phân nhánh `non-sealed`.

### Bước 4 — Biên dịch để tìm nơi thiếu case

Chạy build, đặc biệt các `switch expressions` trên `TaskCommand`. Các nơi không có `default` có thể được compiler chỉ ra là chưa xử lý subtype mới.

Không sửa máy móc bằng một `default` chung. Với mỗi consumer, quyết định lệnh `ArchiveTask` phải được thực thi, ghi nhận, chuyển đổi, từ chối hay xử lý như dữ liệu không áp dụng.

### Bước 5 — Thực thi logic có kiểm soát

Kiểm tra quyền **trước side effect**, kiểm tra trạng thái, thực hiện mutation nguyên tử theo kiến trúc lưu trữ. Trả kết quả có ý nghĩa và xử lý ngoại lệ theo hợp đồng.

### Bước 6 — Bổ sung test cả đường thành công và thất bại

Thêm test ADMIN/USER, ID hợp lệ/blank, task tồn tại/không tồn tại, task active/archived; chạy lại bộ test của ba command cũ.

### Bước 7 — Kiểm tra tương thích và phát hành

Nếu command đi qua REST, queue, event log hoặc file, cập nhật mapper/schema, kiểm tra consumer cũ, thời điểm rollout và dữ liệu đã lưu. Có thể cần triển khai consumer hỗ trợ version mới trước khi producer bắt đầu gửi command mới.

## 9. Ví dụ Java 21 chạy độc lập: thêm ArchiveTask an toàn

Tạo tệp **`SafeCommandExtensionDemo.java`**. Chương trình minh họa một hệ xử lý command chạy **tuần tự trong một tiến trình**, dùng `LinkedHashMap` làm kho lưu tạm để có kết quả xác định. Nó không triển khai transaction hoặc xác thực người dùng thực tế; những vấn đề đó được phân tích ở phần 11.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

public class SafeCommandExtensionDemo {
    enum Role {
        USER, ADMIN
    }

    sealed interface TaskCommand
            permits CreateTask, RenameTask, CompleteTask, ArchiveTask {}

    record CreateTask(String id, String title)
            implements TaskCommand {
        CreateTask {
            requireNonBlank(id, "id");
            requireNonBlank(title, "title");
        }
    }

    record RenameTask(String id, String newTitle)
            implements TaskCommand {
        RenameTask {
            requireNonBlank(id, "id");
            requireNonBlank(newTitle, "newTitle");
        }
    }

    record CompleteTask(String id)
            implements TaskCommand {
        CompleteTask {
            requireNonBlank(id, "id");
        }
    }

    // Command mới được thêm có chủ đích.
    record ArchiveTask(String id)
            implements TaskCommand {
        ArchiveTask {
            requireNonBlank(id, "id");
        }
    }

    record Task(
            String id,
            String title,
            boolean completed,
            boolean archived) {}

    private static final Map<String, Task> TASKS =
            new LinkedHashMap<>();

    static void requireNonBlank(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
    }

    static Task requireActive(String id) {
        Task task = TASKS.get(id);
        if (task == null) {
            throw new IllegalArgumentException(
                    "Task not found: " + id);
        }
        if (task.archived()) {
            throw new IllegalStateException(
                    "Task is archived: " + id);
        }
        return task;
    }

    static String create(String id, String title) {
        if (TASKS.containsKey(id)) {
            throw new IllegalStateException(
                    "Task already exists: " + id);
        }
        TASKS.put(id, new Task(id, title, false, false));
        return "CREATED:" + id;
    }

    static String rename(String id, String newTitle) {
        Task old = requireActive(id);
        TASKS.put(id, new Task(
                id, newTitle, old.completed(), false));
        return "RENAMED:" + id;
    }

    static String complete(String id) {
        Task old = requireActive(id);
        if (old.completed()) {
            throw new IllegalStateException(
                    "Task already completed: " + id);
        }
        TASKS.put(id, new Task(
                id, old.title(), true, false));
        return "COMPLETED:" + id;
    }

    static String archive(String id) {
        Task old = requireActive(id);
        TASKS.put(id, new Task(
                id, old.title(), old.completed(), true));
        return "ARCHIVED:" + id;
    }

    static String execute(TaskCommand command, Role role) {
        if (role == null) {
            throw new IllegalArgumentException(
                    "role must not be null");
        }

        return switch (command) {
            case CreateTask(String id, String title) ->
                    create(id, title);

            case RenameTask(String id, String newTitle) ->
                    rename(id, newTitle);

            case CompleteTask(String id) ->
                    complete(id);

            case ArchiveTask(String id) when role != Role.ADMIN ->
                    throw new SecurityException(
                            "Only ADMIN may archive");

            case ArchiveTask(String id) ->
                    archive(id);

            case null ->
                    throw new IllegalArgumentException(
                            "command must not be null");
        };
    }

    // Chỉ in exception để minh họa các case test.
    static void attempt(String label, Supplier<String> action) {
        try {
            System.out.println(label + " => " + action.get());
        } catch (RuntimeException ex) {
            System.out.println(label + " => "
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        attempt("create", () ->
                execute(new CreateTask("T-1", "Viết bài Java"),
                        Role.USER));

        attempt("rename", () ->
                execute(new RenameTask(
                        "T-1", "Học pattern matching"), Role.USER));

        attempt("complete", () ->
                execute(new CompleteTask("T-1"), Role.USER));

        attempt("archive-user", () ->
                execute(new ArchiveTask("T-1"), Role.USER));

        attempt("archive-admin", () ->
                execute(new ArchiveTask("T-1"), Role.ADMIN));

        attempt("rename-after-archive", () ->
                execute(new RenameTask("T-1", "Đổi tên"),
                        Role.USER));

        attempt("duplicate-create", () ->
                execute(new CreateTask("T-1", "Bản sao"),
                        Role.USER));

        attempt("missing-task", () ->
                execute(new CompleteTask("T-404"), Role.USER));

        attempt("null-command", () ->
                execute(null, Role.ADMIN));

        attempt("blank-id", () ->
                execute(new ArchiveTask(" "), Role.ADMIN));

        System.out.println("state => " + TASKS.get("T-1"));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 -encoding UTF-8 SafeCommandExtensionDemo.java
java SafeCommandExtensionDemo
```

**Standard output mong đợi:**

```text
create => CREATED:T-1
rename => RENAMED:T-1
complete => COMPLETED:T-1
archive-user => SecurityException: Only ADMIN may archive
archive-admin => ARCHIVED:T-1
rename-after-archive => IllegalStateException: Task is archived: T-1
duplicate-create => IllegalStateException: Task already exists: T-1
missing-task => IllegalArgumentException: Task not found: T-404
null-command => IllegalArgumentException: command must not be null
blank-id => IllegalArgumentException: id must not be blank
state => Task[id=T-1, title=Học pattern matching, completed=true, archived=true]
```

### Đối chiếu từng nhóm kết quả

1. `create` tạo task mới và trả `CREATED:T-1`. `rename` giữ ID, đổi title thành `Học pattern matching`. `complete` chuyển `completed` từ `false` sang `true`.
2. `archive-user` khớp `ArchiveTask` nhưng guard `role != Role.ADMIN` đúng, nên ném `SecurityException`. Vì `archive(id)` không được gọi, công việc **chưa** bị lưu trữ ở bước này.
3. `archive-admin` có role ADMIN, guard từ chối sai; case `ArchiveTask` phía sau được chọn, lưu trữ thành công và trả `ARCHIVED:T-1`.
4. `rename-after-archive` tìm được task nhưng `requireActive` phát hiện `archived=true` nên ném `IllegalStateException`.
5. `duplicate-create` phát hiện ID `T-1` đã tồn tại nên không thay thế công việc. `missing-task` từ chối `T-404` không tồn tại.
6. `null-command` chọn `case null` và ném `IllegalArgumentException`. `blank-id` bị từ chối ngay trong compact constructor của `ArchiveTask` **trước khi `execute` được gọi**.
7. Dòng cuối in record `Task`. Title và trạng thái sau cùng được bảo toàn: `completed=true`, `archived=true`. Các lần gọi thất bại ở phía trên không ghi thay đổi vào map.

**Lưu ý về demo:** `attempt` bắt `RuntimeException` để in **lỗi dự kiến** như một bài kiểm thử thủ công, không có nghĩa là handler đã biến lỗi thành thành công. Trong production, bắt mọi `RuntimeException` rồi trả HTTP 200 hoặc `"OK"` là điều cần tránh; tầng biên phải ánh xạ lỗi theo chính sách và giữ khả năng quan sát của lỗi.

## 10. Ma trận kiểm thử khi thêm command

Không chỉ test một lệnh `ArchiveTask` thành công với ADMIN; phải xác minh đường từ chối và các command trước đó.

| Tình huống | Kết quả mong đợi | Mục đích |
| --- | --- | --- |
| `CreateTask("T-1", validTitle)` với ID mới | `CREATED` | Hành vi cũ vẫn chạy. |
| `RenameTask` với task active | `RENAMED` | Thay đổi title không làm mất completed state. |
| `CompleteTask` lần đầu | `COMPLETED` | Trạng thái hoàn thành đúng. |
| `ArchiveTask` với role USER | `SecurityException`, không mutate | Guard quyền và thứ tự case. |
| `ArchiveTask` với ADMIN, task active | `ARCHIVED` | Command mới được thực thi. |
| Rename sau archive | `IllegalStateException` | Quy tắc trạng thái. |
| Create lại ID cũ | `IllegalStateException` | Chống ghi đè task hiện có. |
| Complete ID không tồn tại | `IllegalArgumentException` | Tham chiếu dữ liệu sai. |
| Command `null` | `IllegalArgumentException` | Chính sách selector null. |
| ID blank hoặc null trong record | `IllegalArgumentException` | Validation ngay tại constructor. |
| Archive lặp lại | `IllegalStateException` theo demo | Hợp đồng chưa idempotent; cần quyết định cho production. |
| Complete lần hai | `IllegalStateException` theo demo | Chống thao tác lặp trái chính sách hiện tại. |

### Unit test ví dụ với JUnit Jupiter

Đoạn sau chỉ **minh họa test riêng**, cần cấu hình JUnit Jupiter trong dự án. Nó giả định `SafeCommandExtensionDemo` được biên dịch cùng package, và chỉ gọi thao tác không làm phụ thuộc kết quả vào trạng thái `TASKS` của test khác.

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class SafeCommandExtensionDemoTest {
    @Test
    void archiveRequiresAdmin() {
        var command = new SafeCommandExtensionDemo.ArchiveTask("A-1");

        assertThrows(SecurityException.class,
                () -> SafeCommandExtensionDemo.execute(
                        command,
                        SafeCommandExtensionDemo.Role.USER));
    }

    @Test
    void blankIdIsRejectedBeforeDispatch() {
        assertThrows(IllegalArgumentException.class,
                () -> new SafeCommandExtensionDemo.ArchiveTask(" "));
    }

    @Test
    void nullCommandIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SafeCommandExtensionDemo.execute(
                        null, SafeCommandExtensionDemo.Role.ADMIN));
    }
}
```

Những ca trên chủ yếu kiểm tra lỗi; khi viết bộ test đầy đủ cho hệ thống, nên dùng store riêng từng test hoặc reset/fixture có kiểm soát, không để test phụ thuộc vào trạng thái static từ test khác. Việc xác minh **không mutate khi bị từ chối quyền** cần có cách đọc trạng thái phù hợp, không chỉ `assertThrows`; trong demo, stdout và trạng thái cuối giúp quan sát nhưng chưa thay thế test bất biến trạng thái độc lập.

## 11. Thêm command an toàn trong hệ thống thực tế

### 11.1. Idempotency và yêu cầu được gửi lại

Ở API qua mạng, client có thể gửi cùng một command nhiều lần do timeout/retry, kể cả khi lần đầu đã thực hiện thành công. Trong demo, gọi `CreateTask` lại cùng ID bị từ chối; gọi `ArchiveTask` lần hai cũng bị từ chối. **Đây là chính sách có thể đúng cho một bài tập, nhưng không đủ để coi hệ thống an toàn trước retry.**

Nếu yêu cầu nghiệp vụ hỗ trợ thực thi **idempotent**, cân nhắc:

- Command có **idempotency key** ổn định cho một yêu cầu logic.
- Ghi nhận key và kết quả đã xử lý trong bộ lưu trữ bền vững.
- Khi nhận lại cùng key, trả kết quả đã ghi nhận thay vì làm side effect lần nữa.
- Phân biệt retry của **cùng command** với command mới nhưng trùng nội dung.
- Sử dụng ràng buộc duy nhất/giao dịch để tránh hai request đồng thời cùng “qua cửa” kiểm tra trùng.

Một `Map` trong bộ nhớ và phép kiểm tra `containsKey` rồi `put` **không phải thao tác nguyên tử** khi nhiều thread/server cạnh tranh. Idempotency ở production liên quan đến thiết kế lưu trữ và transaction, không chỉ record/pattern.

### 11.2. Thứ tự và trạng thái nhất quán

Nếu `ArchiveTask` đến trước `CreateTask` qua message queue, handler có thể báo ID chưa tồn tại. Nếu hai command đến gần như đồng thời, cần có chính sách **ordering**, phiên bản đối tượng hoặc concurrency control.

Ví dụ optimistic locking có thể dựa vào trường `version` của task: handler đọc version dự kiến, chỉ cập nhật nếu version chưa đổi. Khi xảy ra conflict, trả một kết quả có ý nghĩa thay vì im lặng ghi đè. Case study không triển khai lock vì phạm vi là pattern matching, nhưng đây là điều phải kiểm tra trước khi dùng mô hình command trong hệ thống có concurrency.

### 11.3. Authorization ở ranh giới tin cậy

Guard `role != Role.ADMIN` chỉ minh họa một điều kiện. Trong ứng dụng thật:

- Xác minh identity/token và lấy role từ security context đáng tin.
- Phân quyền dựa trên quyền cụ thể hoặc tài nguyên nếu mô hình yêu cầu, không chỉ một enum toàn cục.
- Đảm bảo các entry point khác (batch job, CLI, queue consumer) không bypass kiểm tra.
- Thực hiện kiểm tra trước khi mutate và audit các hành động quan trọng.

Không coi một dòng `when` là thay thế hoàn chỉnh cho hệ thống bảo mật.

### 11.4. Versioning command payload

Khi command được truyền qua REST/queue/JSON, subtype Java trong một module không tự mô tả toàn bộ hợp đồng truyền tin. Cần quản lý:

- **Discriminator** ổn định, ví dụ loại `"ARCHIVE_TASK"` trong schema bên ngoài.
- Những trường bắt buộc/tùy chọn, giá trị mặc định và quy tắc validation.
- Phiên bản schema hoặc chiến lược tương thích khi thêm trường.
- Client/consumer phiên bản cũ gặp command mới thì **từ chối rõ** hoặc được nâng cấp trước khi nhận, không xử lý như thành công.
- Lệnh và event khác nhau: command là yêu cầu, event `TaskArchived` (nếu phát ra sau khi thực thi) mô tả kết quả đã xảy ra.

Nếu triển khai rolling upgrade, một trình tự thường an toàn là **nâng cấp consumer để hiểu command mới trước**, rồi mới mở producer gửi command đó. Quy trình thực tế phụ thuộc message broker, deployment topology và yêu cầu backward compatibility.

### 11.5. Transaction, side effect và outbox

Nếu archive vừa cập nhật database vừa phát event, cần nghĩ đến việc **chỉ một trong hai bước thành công**. Một transaction trên database cộng với **transactional outbox** là một lựa chọn để đồng bộ trạng thái và ý định phát event, kết hợp consumer idempotent. Record patterns không tự giải quyết vấn đề giao dịch phân tán.

Trong chương trình demo, chỉ có một map, không có database hay event bus; dùng nó để học cách thêm command mà compiler có thể kiểm tra, **không** coi đây là kiến trúc triển khai đa máy hoàn chỉnh.

## 12. Những lỗi phổ biến khi mở rộng Command hierarchy

### Lỗi 1 — Thêm record nhưng quên permits

`record ArchiveTask(String id) implements TaskCommand` sẽ không được phép trực tiếp triển khai một `sealed interface` nếu không nằm trong tập `permits` hợp lệ. Cách sửa là cập nhật hệ kiểu có chủ đích, không bỏ `sealed` chỉ để “dễ thêm”.

### Lỗi 2 — Thêm permits nhưng không cập nhật tất cả dispatchers

Khi handler là `switch expression` exhaustive không có `default`, compiler có thể chỉ ra case còn thiếu khi biên dịch lại. Không chữa bằng `default -> "SUCCESS"`. Tùy consumer, hãy xử lý, từ chối hoặc chuyển tiếp `ArchiveTask` theo hợp đồng cụ thể.

### Lỗi 3 — Đặt case tổng quát trước guard cụ thể

```java
// Sai thứ tự nếu muốn kiểm tra role riêng cho ArchiveTask:
// case ArchiveTask(String id) -> archive(id);
// case ArchiveTask(String id) when role != Role.ADMIN ->
//         throw new SecurityException("Denied");
```

Nhánh đầu không guard bao phủ mọi `ArchiveTask`, làm nhánh sau bị **dominated** và có thể gây lỗi biên dịch. Luôn đặt nhánh có guard cụ thể **trước** nhánh rộng hơn, đồng thời test trường hợp guard đúng/sai.

### Lỗi 4 — Kiểm tra quyền sau khi mutate

Từ chối sau khi đã lưu trữ không khôi phục trạng thái tự động. Viết handler có kiểm soát trước side effect và dùng transaction khi có nhiều bước ghi.

### Lỗi 5 — Chỉ kiểm tra input bằng pattern mà bỏ validation

`case CreateTask(String id, String title)` xác nhận các component khớp type pattern, nhưng không chứng minh `id` hoặc `title` không blank, đúng giới hạn độ dài hay hợp lệ theo domain. Constructor hoặc boundary vẫn phải validate nội dung.

### Lỗi 6 — Cho rằng default bắt cả null

Selector `null` trong pattern-matching `switch` có quy tắc riêng. Nếu command null là lỗi, dùng `case null -> throw ...` hoặc kiểm tra trước `switch`. Không để ngoại lệ xảy ra ngẫu nhiên rồi mới bắt chung.

### Lỗi 7 — Tái sử dụng command làm event

Một `ArchiveTask` là **đề nghị lưu trữ**; `TaskArchived` là **sự kiện lưu trữ đã thành công**. Gửi command như event có thể khiến consumer giả định thao tác đã được chấp nhận dù handler chưa xác thực quyền và trạng thái.

### Lỗi 8 — Kết luận “đã an toàn” vì có sealed

Sealed giúp giới hạn direct subtypes, còn an toàn nghiệp vụ đòi hỏi kiểm tra role, trạng thái, transaction, retry, idempotency, tính tương thích và observability. Tránh nhầm compile-time exhaustiveness với một bảo đảm runtime end-to-end.

## 13. Đánh đổi: sealed hierarchy hay interface mở?

Cách tiếp cận trong bài thích hợp khi **module chủ sở hữu kiểm soát tập command** và mong các dispatcher phải cập nhật khi xuất hiện command mới.

Nếu dự án công bố một **plugin API** cho bên thứ ba bổ sung command/handler mà không sửa lõi, một `interface` mở và cơ chế đăng ký handler có thể phù hợp hơn. Với interface mở, compiler không thể mặc nhiên chứng minh rằng vài case cụ thể đã bao phủ mọi implementation tương lai; cần fallback hoặc dispatch dựa vào hợp đồng chung.

Không nên bỏ sealed chỉ vì “có thể sau này thêm lệnh”; khi module chủ sở hữu vẫn kiểm soát mọi lệnh, mở rộng `permits` và cập nhật nơi xử lý là một quy trình có kiểm soát. Ngược lại, đừng ép plugin của bên thứ ba vào tập `permits` đóng nếu chính thiết kế yêu cầu extensibility độc lập.

Đặc biệt, dùng **polymorphism** cũng là lựa chọn có giá trị:

```java
interface CommandHandler<T> {
    String handle(T command);
}
```

Đây chỉ là hợp đồng minh họa, chưa có registry hoặc cách chọn handler. Nếu xử lý nghiệp vụ đã được đóng gói riêng trong các handler, một registry có kiểm tra thiếu handler có thể tốt hơn một `switch` lớn. Nhưng registry kiểu mở phải chủ động phát hiện command chưa đăng ký và xử lý lỗi rõ ràng; nó không thừa hưởng exhaustiveness của sealed switch.

## 14. Checklist review một pull request thêm command

1. **Ý nghĩa domain:** Command mới biểu diễn một ý định duy nhất, có tên rõ, không lẫn với event?
2. **Schema:** Record chứa dữ liệu tối thiểu cần thiết và có validation cho null/blank/range?
3. **Hierarchy:** `permits` được cập nhật đúng module/package; không làm hỏng các subtype cũ?
4. **Dispatch:** Mỗi `switch`/handler phải có case rõ cho subtype mới hoặc một chính sách từ chối có chủ đích?
5. **Guard:** Nhánh có guard đặt trước nhánh tổng quát; guard true/false đều được kiểm thử?
6. **Authorization:** Role lấy từ nguồn tin cậy, kiểm tra trước mutation?
7. **State transitions:** Command có áp dụng được với task đang tồn tại, đã hoàn thành hoặc đã lưu trữ?
8. **Failure:** Các lỗi không bị chuyển thành thành công giả; exception/result type có ý nghĩa?
9. **Atomicity:** Có tránh cập nhật một phần, xử lý race/transaction theo kiến trúc lưu trữ?
10. **Retry/idempotency:** Có chính sách cho command gửi lại, command đồng thời hoặc trùng ID?
11. **Compatibility:** Producer, consumer, serializer, schema và dữ liệu cũ được nâng cấp theo trình tự thích hợp?
12. **Tests:** Có test mới và regression test cho mọi command cũ, bao gồm trạng thái sau thất bại?
13. **Build:** Biên dịch bằng Java 21 chính thức, không vô tình dựa vào cú pháp preview?
14. **Observability:** Có log/metric/audit phù hợp mà không làm lộ dữ liệu nhạy cảm?
15. **Ownership:** Ai duy trì tập command và quyết định khi nào thêm subtype tiếp theo?

## 15. Tự kiểm tra

**Câu 1.** Vì sao sau khi thêm `ArchiveTask` vào `permits TaskCommand`, một `switch expression` chỉ có ba case cũ có thể không biên dịch?

**Đáp án:** Vì hierarchy đóng nay có thêm subtype được phép. Nếu không có case bao quát, compiler Java 21 có thể phát hiện biểu thức `switch` chưa exhaustive. Đây là tín hiệu cần thiết để cập nhật dispatcher.

**Câu 2.** Tại sao không nên thêm `default -> "OK"` chỉ để sửa lỗi thiếu case?

**Đáp án:** Command mới có thể bị bỏ qua mà caller tưởng đã thực thi. Nếu command không hỗ trợ, phải trả lỗi/ý nghĩa rõ, không báo thành công giả.

**Câu 3.** Với:

```java
case ArchiveTask(String id) when role != Role.ADMIN ->
        throw new SecurityException("Only ADMIN may archive");
case ArchiveTask(String id) ->
        archive(id);
```

điều gì xảy ra với `Role.USER` và `Role.ADMIN`?

**Đáp án:** Với USER, guard đầu đúng và ném `SecurityException`; không gọi `archive`. Với ADMIN, guard đầu sai, Java tiếp tục xét case thứ hai rồi gọi `archive`, với điều kiện domain state hợp lệ. Đoạn code là snippet trong `switch`, không phải tệp chạy độc lập.

**Câu 4.** Khi nào một command được coi là idempotent?

**Đáp án:** Khi thực hiện lại cùng một **yêu cầu logic** theo hợp đồng không tạo thêm side effect không mong muốn. Trong một API có retry, thường cần idempotency key và cơ chế lưu kết quả/đảm bảo uniqueness. Demo cố ý từ chối archive lại nên không thể tự nhận là có cơ chế idempotent hoàn chỉnh.

**Câu 5.** Vì sao `ArchiveTask` không nên dùng làm sự kiện `TaskArchived`?

**Đáp án:** Lệnh là yêu cầu có thể thất bại; event là thông tin rằng một thao tác đã xảy ra. Đổi tên khái niệm không giải quyết được việc kiểm tra quyền, trạng thái và kết quả ghi.

## 16. Tài liệu nền

- **JEP 409 – Sealed Classes:** https://openjdk.org/jeps/409
- **JEP 440 – Record Patterns:** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for switch:** https://openjdk.org/jeps/441
- **Oracle Java 21 – Pattern Matching for switch:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- **Java Language Specification 21, `14.30 – Patterns:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30

**Ghi nhớ:** Thêm command an toàn là một **thay đổi xuyên suốt hợp đồng**: kiểu lệnh, `permits`, dispatcher, quyền, validation, trạng thái, test và khả năng tương thích phải được cập nhật nhất quán. **Java 21 sealed interface + record patterns + exhaustive switch** giúp compiler phát hiện nhiều nơi thiếu nhánh và làm logic phân loại dễ đọc; nhưng chỉ **authorization trước side effect, quản lý trạng thái/giao dịch và kiểm thử regression** mới làm thay đổi đó an toàn trong ứng dụng thực.
