# Bài tổng hợp trên JDK hiện hành với các kỹ thuật Java 8 còn áp dụng

**Chủ đề:** Java 8 → Thực hành → Bài tổng hợp trên JDK hiện hành với các kỹ thuật Java 8 còn áp dụng.

Bài này xây dựng một ứng dụng quản lý công việc nhỏ (Task Board) để ghép các kỹ thuật Java 8 thành một chương trình có cấu trúc rõ ràng: mô hình dữ liệu bất biến, kiểm tra đầu vào, repository tra cứu, xử lý ngày tháng, lọc và tổng hợp dữ liệu, sắp xếp theo nhiều tiêu chí, tìm kiếm có thể vắng mặt và chạy các báo cáo độc lập bất đồng bộ.

Mục tiêu là dùng những API Java 8 vẫn có giá trị trong ứng dụng hiện đại, sau đó biên dịch bằng một JDK mới với mức API Java 8. Cách làm này hữu ích khi một hệ thống cần chạy trên nhiều runtime hoặc đang nâng cấp JDK nhưng chưa muốn nâng baseline ngôn ngữ/API của ứng dụng.

## 1. Chọn đúng JDK và mức tương thích

Tại ngày **06/11/2026**, trang tải JDK của Oracle liệt kê:

- **JDK 27** là bản feature release mới nhất.
- **JDK 25** là bản Long-Term Support (LTS) mới nhất.

JDK feature release nhận các cải tiến mới theo chu kỳ phát hành; bản LTS phù hợp hơn khi tổ chức cần một mốc hỗ trợ dài hạn. Lựa chọn runtime production còn phụ thuộc chính sách hỗ trợ của vendor, hệ điều hành, thư viện và tổ chức.

Ứng dụng trong bài chỉ dùng API có từ Java 8, vì vậy có thể:

- Biên dịch trực tiếp bằng JDK 8.
- Hoặc dùng JDK mới và `javac --release 8` để kiểm tra source, bytecode và API surface tương thích Java 8.

**Môi trường kiểm thử thực tế của bài:** Azul OpenJDK 24.0.2. Chương trình đã biên dịch thành công với `javac --release 8`, chạy trên JDK 24.0.2 và `javap` xác nhận bytecode `major version: 52` (Java 8). Bài không tuyên bố đã chạy chương trình trên JDK 27 hoặc JDK 8 runtime.

Điểm phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| JDK dùng để biên dịch | Bộ compiler và công cụ đang chạy, ví dụ JDK 24 hoặc 27 |
| `--release 8` | Giới hạn ngôn ngữ/bytecode/API theo Java 8 |
| Bytecode major version 52 | Class file target Java 8 |
| Runtime chạy chương trình | JVM thực tế nạp class file; trong lần kiểm thử này là JDK 24.0.2 |
| JDK hiện hành | Phiên bản mới nhất tại thời điểm tra cứu; không đồng nghĩa với JDK đang cài trên máy |

**Không dùng `-source 8 -target 8` một mình để thay cho `--release 8` khi biên dịch bằng JDK mới.** Hai tùy chọn source/target không tự giới hạn các API mà compiler nhìn thấy; có thể vô tình gọi method chỉ tồn tại từ Java 9 trở lên rồi tạo class file Java 8 nhưng không chạy được trên Java 8. `--release` giải quyết cả giới hạn API.

Trên JDK 8, compiler chưa có tùy chọn `--release`; dùng compiler JDK 8 trực tiếp để bảo đảm API baseline.

## 2. Bài toán thực hành

Task Board quản lý các công việc kỹ thuật. Mỗi công việc có:

- Mã công việc.
- Tiêu đề.
- Nhóm phụ trách: `PLATFORM`, `WEB`, `QA`.
- Trạng thái: `TODO`, `IN_PROGRESS`, `DONE`.
- Mức ưu tiên: `HIGH`, `MEDIUM`, `LOW`.
- Ngày đến hạn.
- Thời lượng ước tính, tính bằng phút.

Ứng dụng cần thực hiện:

1. Kiểm tra dữ liệu bắt buộc và thời lượng không âm.
2. Từ chối mã công việc trùng nhau.
3. Tra cứu một công việc bằng ID và biểu diễn trường hợp không tìm thấy.
4. Xác định công việc còn hoạt động, quá hạn và sắp đến hạn.
5. Đếm số công việc theo trạng thái.
6. Tổng hợp phút ước tính còn lại theo nhóm.
7. Lọc công việc ưu tiên cao nhưng chưa hoàn thành.
8. Sắp xếp công việc quá hạn theo ưu tiên, ngày đến hạn và ID.
9. Chạy hai báo cáo độc lập bằng `CompletableFuture`.
10. Đóng executor đúng vòng đời và kiểm tra kết quả bằng assertion.

Dữ liệu demo được cố định ở ngày **2025-03-10** để stdout luôn lặp lại được. Trong ứng dụng thực, ngày hiện tại sẽ đến từ `Clock.systemDefaultZone()` hoặc một Clock được cấu hình theo múi giờ nghiệp vụ.

## 3. Các kỹ thuật Java 8 được kết hợp

| Kỹ thuật | Nơi sử dụng | Giá trị trong ứng dụng |
|---|---|---|
| Lambda và method reference | Predicate, Stream, Comparator | Mô tả quy tắc lọc/chuyển đổi ngắn gọn |
| Functional interfaces | `Predicate<Task>` | Ghép điều kiện bằng `and` |
| Default method trong interface | `TaskView.isActive()` | Chia sẻ hành vi mặc định |
| Static method trong interface | `TaskView.hasText()` | Đặt helper liên quan trực tiếp đến abstraction |
| Immutable class | `Task` | Dữ liệu an toàn khi nhiều báo cáo cùng đọc |
| `Map.putIfAbsent` | Repository | Phát hiện ID trùng |
| `Optional` | `findById`, kết quả tìm công việc | Biểu diễn rõ trường hợp không có dữ liệu |
| `java.time` | `LocalDate`, `Clock` | Xử lý ngày hạn và kiểm thử thời gian xác định |
| Stream API | Lọc, nhóm, sắp xếp | Tạo báo cáo từ cùng một nguồn |
| Collectors | `groupingBy`, `counting`, `summingInt` | Tích lũy số liệu theo nhóm |
| Comparator | Xếp thứ tự nhiều tiêu chí | Tạo kết quả có tie-breaker rõ ràng |
| CompletableFuture | Chạy báo cáo độc lập | Kết hợp các kết quả bất đồng bộ |
| ExecutorService | Quản lý worker threads | Kiểm soát executor và đóng tài nguyên |

Tất cả API dùng trong chương trình chính đều thuộc Java 8. Không dùng `record`, `var`, `List.of`, `Stream.toList`, `Optional.stream`, switch expression hoặc `ExecutorService.close()`.

## 4. Luồng xử lý tổng thể

~~~text
Input tasks
    |
    v
Validate Task objects
    |
    v
TaskRepository
  - index by ID
  - reject duplicate IDs
  - expose Optional lookup
    |
    v
Immutable task snapshot
    |
    +------------------------------+
    |                              |
    v                              v
Count by status              Find overdue tasks
(groupingBy + counting)      (filter + sorted)
    |                              |
    +---------------+--------------+
                    |
                    v
             CompletableFuture
               allOf(...).join()
                    |
                    v
             Combine report output

Other synchronous views:
  - active minutes by team
  - next upcoming task
  - urgent active count
~~~

Các báo cáo chỉ đọc cùng một danh sách task bất biến. Không có thread nào sửa collection trong lúc Stream đang duyệt, do đó không cần đồng bộ hóa dữ liệu báo cáo.

## 5. Mô hình dữ liệu và interface Java 8

### 5.1. Default method và static method

Java 8 cho phép interface có `default` method và `static` method.

~~~java
interface TaskView {
    String getId();
    Status getStatus();

    default boolean isActive() {
        return getStatus() != Status.DONE;
    }

    static boolean hasText(String value) {
        return value != null && !value.trim().isEmpty();
    }
}
~~~

- `isActive()` là hành vi mặc định. Class implement interface có thể dùng trực tiếp hoặc override khi có quy tắc riêng.
- `hasText()` là static method của interface, gọi bằng `TaskView.hasText(...)`; static method không được kế thừa như default method.
- Interface vẫn khai báo các method trừu tượng mà implementation phải cung cấp.

Dùng default method khi một hành vi có ý nghĩa chung cho các implementation. Không biến interface thành một nơi chứa mọi helper không liên quan đến abstraction.

### 5.2. Vì sao Task là immutable?

`Task` có các thuộc tính `private final`, constructor kiểm tra đầu vào và không có setter. Các kiểu field được chọn đều bất biến hoặc enum: `String`, `LocalDate`, enum và `int`.

Một task sau khi tạo không thay đổi trạng thái. Nếu cần chuyển trạng thái, ứng dụng tạo một Task mới với dữ liệu mới. Cách này giúp:

- Dễ đọc và kiểm thử.
- Giảm lỗi khi nhiều báo cáo cùng đọc.
- Tránh thay đổi object giữa lúc Stream đang chạy.
- Dễ chia sẻ dữ liệu qua executor.

Immutable object không tự làm cho toàn bộ chương trình thread-safe; collection và các tài nguyên khác vẫn cần có vòng đời/ownership rõ ràng.

### 5.3. Validation ở constructor

Ví dụ kiểm tra:

- ID và title không được null/rỗng/toàn khoảng trắng.
- `team`, `status`, `priority`, `dueDate` không được null.
- `estimateMinutes` không được âm.

Đây là validation bất biến của domain model. Quy tắc phụ thuộc nghiệp vụ như “không được hoàn thành task sau ngày release” nên đặt ở service/domain policy phù hợp, không nhồi tất cả vào constructor.

## 6. Repository và Optional

Repository lập chỉ mục task bằng ID:

~~~java
Map<String, Task> index = new LinkedHashMap<String, Task>();

for (Task task : tasks) {
    Task previous = index.putIfAbsent(task.getId(), task);
    if (previous != null) {
        throw new IllegalArgumentException("duplicate task id");
    }
}
~~~

`putIfAbsent` là method của `Map` có từ Java 8. Nó chỉ thêm mapping khi key chưa có giá trị. Với repository này, ID trùng là lỗi dữ liệu nên chương trình từ chối ngay khi tạo repository.

Tra cứu trả về:

~~~java
Optional<Task> findById(String id) {
    return Optional.ofNullable(byId.get(id));
}
~~~

`Optional<Task>` thể hiện rõ rằng kết quả có thể không tồn tại. Caller xử lý bằng `map`, `orElse`, `orElseGet`, `ifPresent` hoặc `orElseThrow`.

~~~java
String title = repository.findById("T-999")
        .map(Task::getTitle)
        .orElse("not found");
~~~

Không trả `null` từ một method được thiết kế để trả `Optional`. Không dùng `Optional` làm field bắt buộc trong mọi entity; nó thường phù hợp nhất ở return type của API tra cứu.

## 7. Ngày đến hạn và Clock

Dùng `LocalDate` cho ngày đến hạn vì nghiệp vụ chỉ quan tâm ngày lịch, không phải một thời điểm tuyệt đối có offset.

~~~java
LocalDate dueDate = LocalDate.of(2025, 3, 10);
~~~

Không lấy ngày trực tiếp bằng `LocalDate.now()` ở nhiều nơi trong business logic. Inject `Clock`:

~~~java
final class TaskReports {
    private final Clock clock;

    TaskReports(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    LocalDate today() {
        return LocalDate.now(clock);
    }
}
~~~

Production có thể truyền:

~~~java
Clock.systemDefaultZone()
~~~

Test có thể truyền:

~~~java
Clock.fixed(
        LocalDate.of(2025, 3, 10)
                .atStartOfDay(ZoneOffset.UTC).toInstant(),
        ZoneOffset.UTC)
~~~

Clock cố định làm cho các điều kiện “quá hạn”, “đến hạn hôm nay” và “sắp đến hạn” xác định. Test không còn phụ thuộc ngày máy chạy.

**Lưu ý timezone:** `LocalDate` không chứa timezone. Khi nghiệp vụ xác định ngày theo một vùng như `Asia/Ho_Chi_Minh`, hãy chọn zone rõ ràng ở nơi chuyển từ `Instant` sang `LocalDate`. Đừng để timezone mặc định của máy chủ quyết định ngày nghiệp vụ một cách vô tình.

## 8. Lambda, Predicate và method reference

Điều kiện task còn hoạt động được biểu diễn bằng `Predicate<Task>`:

~~~java
Predicate<Task> urgentActive = Task::isActive;
urgentActive = urgentActive.and(
        task -> task.getPriority() == Priority.HIGH);

long urgentCount = tasks.stream()
        .filter(urgentActive)
        .count();
~~~

- `Task::isActive` là method reference.
- Lambda tiếp theo kiểm tra priority.
- `Predicate.and` kết hợp hai điều kiện theo logic AND.
- `filter` chỉ giữ task thỏa cả hai điều kiện.

Các functional interface phổ biến khác:

| Interface | Input | Output | Trường hợp dùng |
|---|---|---|---|
| `Predicate<T>` | T | boolean | Điều kiện lọc |
| `Function<T,R>` | T | R | Chuyển đổi |
| `Consumer<T>` | T | void | Thực hiện hành động |
| `Supplier<T>` | Không | T | Cung cấp giá trị |
| `UnaryOperator<T>` | T | T | Biến đổi cùng kiểu |
| `BiFunction<T,U,R>` | T, U | R | Kết hợp hai giá trị |

Ưu tiên method reference khi nó làm rõ ý định; dùng lambda khi cần biểu đạt logic nhiều bước hoặc nhiều tham số.

## 9. Stream và Collector trong báo cáo

### 9.1. Đếm task theo trạng thái

~~~java
Map<Status, Long> countByStatus =
        tasks.stream().collect(Collectors.groupingBy(
                Task::getStatus,
                () -> new EnumMap<Status, Long>(Status.class),
                Collectors.counting()));
~~~

- `groupingBy` tạo nhóm theo trạng thái.
- `EnumMap` phù hợp với enum key và có thứ tự theo khai báo enum.
- `counting` trả về `Long`.

### 9.2. Tổng phút ước tính theo nhóm

~~~java
Map<Team, Integer> activeMinutesByTeam =
        tasks.stream()
                .filter(Task::isActive)
                .collect(Collectors.groupingBy(
                        Task::getTeam,
                        () -> new EnumMap<Team, Integer>(Team.class),
                        Collectors.summingInt(
                                Task::getEstimateMinutes)));
~~~

Báo cáo chỉ tính task chưa DONE. Nếu tổng phút có thể vượt giới hạn `int`, dùng `summingLong` và kiểu `Long`.

### 9.3. Lọc công việc quá hạn

~~~java
LocalDate asOf = today();

List<Task> overdue = tasks.stream()
        .filter(task -> task.isOverdue(asOf))
        .sorted(order)
        .collect(Collectors.toList());
~~~

Chụp `asOf` một lần trước pipeline để toàn bộ báo cáo dùng cùng một ngày. Nếu gọi clock trong từng phần tử, một pipeline chạy qua thời điểm nửa đêm có thể áp dụng hai ngày khác nhau.

### 9.4. Comparator nhiều tiêu chí

Quy tắc xếp công việc quá hạn:

1. Priority HIGH trước MEDIUM, MEDIUM trước LOW.
2. Cùng priority thì ngày đến hạn sớm hơn trước.
3. Cùng ngày thì ID tăng dần.

~~~java
Comparator<Task> order = Comparator
        .comparingInt((Task task) -> task.getPriority().getRank())
        .thenComparing(Task::getDueDate)
        .thenComparing(Task::getId);
~~~

Priority dùng rank tường minh thay vì `ordinal()`. Thứ tự enum có thể bị thay đổi khi sửa source; một rank nghiệp vụ tường minh làm ý định rõ hơn.

Thêm tie-breaker giúp thứ tự báo cáo ổn định. Nếu chỉ so priority và ngày, các task cùng hai giá trị đó có thể giữ thứ tự encounter của nguồn.

### 9.5. Task sắp đến hạn tiếp theo

~~~java
Optional<Task> nextUpcoming = tasks.stream()
        .filter(Task::isActive)
        .filter(task -> !task.getDueDate().isBefore(asOf))
        .min(Comparator.comparing(Task::getDueDate)
                .thenComparingInt(
                        task -> task.getPriority().getRank())
                .thenComparing(Task::getId));
~~~

Báo cáo loại task đã quá hạn, sau đó tìm ngày đến hạn gần nhất trong các task còn hoạt động. Nếu hai task cùng ngày, priority cao hơn đứng trước.

`min` trả `Optional<Task>` vì có thể không còn task nào phù hợp.

## 10. CompletableFuture và ExecutorService

Hai báo cáo độc lập — đếm theo trạng thái và lấy danh sách quá hạn — có thể chạy song song.

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);

try {
    CompletableFuture<Map<Status, Long>> countsFuture =
            CompletableFuture.supplyAsync(
                    () -> reports.countByStatus(tasks),
                    executor);

    CompletableFuture<String> overdueFuture =
            CompletableFuture.supplyAsync(
                    () -> reports.overdue(tasks),
                    executor)
                    .thenApply(TaskBoardDemo::ids);

    CompletableFuture.allOf(
            countsFuture, overdueFuture).join();

    Map<Status, Long> counts = countsFuture.join();
    String overdueIds = overdueFuture.join();
} finally {
    shutdown(executor);
}
~~~

### 10.1. Vì sao truyền Executor tường minh?

Overload `supplyAsync(supplier)` không có executor sử dụng default asynchronous execution facility, thường là `ForkJoinPool.commonPool()`.

Dùng `supplyAsync(supplier, executor)` giúp ứng dụng:

- Kiểm soát số thread.
- Phân tách workload báo cáo khỏi common pool.
- Quản lý lifecycle executor.
- Cấu hình riêng cho tác vụ I/O hoặc CPU khi ứng dụng mở rộng.

Ví dụ này dùng hai thread vì có hai báo cáo độc lập. Kích thước pool thực tế phải dựa vào workload, độ chờ I/O, CPU và giới hạn tài nguyên.

### 10.2. allOf và join

`CompletableFuture.allOf(...)` tạo một future hoàn thành khi tất cả future đầu vào hoàn thành. Nó không tự trả về danh sách kết quả có kiểu; sau khi `allOf` hoàn thành, đọc từng future bằng `join()`.

`join()` không khai báo checked exception; nếu stage thất bại, nó ném `CompletionException`. Nếu cần xử lý `InterruptedException`, `ExecutionException` hoặc timeout bằng checked exception, dùng `get()` hoặc `get(timeout, unit)` phù hợp.

### 10.3. Non-async và async continuation

- `thenApply(...)` có thể chạy trên thread hoàn thành stage trước đó hoặc thread gọi thao tác completion.
- `thenApplyAsync(...)` dùng asynchronous execution facility mặc định.
- `thenApplyAsync(..., executor)` dùng executor được truyền.

Không giả định mọi callback đều chạy trên một thread riêng. Chọn async hay non-async theo công việc và latency, không theo tên method.

### 10.4. Đóng executor

`shutdown()` ngừng nhận task mới nhưng cho task đã submit chạy xong. `awaitTermination` chờ executor kết thúc. Nếu quá thời hạn, `shutdownNow()` yêu cầu dừng các task đang chạy và trả lại task đang chờ; đây là nỗ lực best-effort, không bảo đảm mọi tác vụ lập tức dừng.

Khi bị interrupt, gọi `shutdownNow()` và khôi phục interrupt status bằng `Thread.currentThread().interrupt()`.

Trong code Java 8, không dùng `try (ExecutorService executor = ...)`: `ExecutorService` chỉ trở thành `AutoCloseable` từ Java 19. Dùng `shutdown`/`awaitTermination` tường minh để giữ tương thích Java 8.

## 11. Chương trình hoàn chỉnh: TaskBoardDemo.java

Chương trình sau là một file độc lập, dùng các API Java 8 và có thể biên dịch bằng JDK mới với `--release 8`.

Lưu thành **`TaskBoardDemo.java`**:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class TaskBoardDemo {
    enum Status { TODO, IN_PROGRESS, DONE }
    enum Team { PLATFORM, WEB, QA }

    enum Priority {
        HIGH(1), MEDIUM(2), LOW(3);

        private final int rank;

        Priority(int rank) {
            this.rank = rank;
        }

        int getRank() {
            return rank;
        }
    }

    interface TaskView {
        String getId();
        Status getStatus();

        default boolean isActive() {
            return getStatus() != Status.DONE;
        }

        static boolean hasText(String value) {
            return value != null && !value.trim().isEmpty();
        }
    }

    static final class Task implements TaskView {
        private final String id;
        private final String title;
        private final Team team;
        private final Status status;
        private final Priority priority;
        private final LocalDate dueDate;
        private final int estimateMinutes;

        Task(String id, String title, Team team, Status status,
             Priority priority, LocalDate dueDate,
             int estimateMinutes) {

            if (!TaskView.hasText(id) || !TaskView.hasText(title)) {
                throw new IllegalArgumentException(
                        "id and title are required");
            }

            if (estimateMinutes < 0) {
                throw new IllegalArgumentException(
                        "estimateMinutes must not be negative");
            }

            this.id = id;
            this.title = title;
            this.team = Objects.requireNonNull(team, "team");
            this.status = Objects.requireNonNull(status, "status");
            this.priority = Objects.requireNonNull(priority, "priority");
            this.dueDate = Objects.requireNonNull(dueDate, "dueDate");
            this.estimateMinutes = estimateMinutes;
        }

        public String getId() {
            return id;
        }

        public String getTitle() {
            return title;
        }

        public Team getTeam() {
            return team;
        }

        public Status getStatus() {
            return status;
        }

        public Priority getPriority() {
            return priority;
        }

        public LocalDate getDueDate() {
            return dueDate;
        }

        public int getEstimateMinutes() {
            return estimateMinutes;
        }

        boolean isOverdue(LocalDate asOf) {
            return isActive() && dueDate.isBefore(asOf);
        }
    }

    static final class TaskRepository {
        private final Map<String, Task> byId;

        TaskRepository(List<Task> tasks) {
            Map<String, Task> index =
                    new java.util.LinkedHashMap<String, Task>();

            for (Task task : tasks) {
                Task previous = index.putIfAbsent(
                        task.getId(), task);

                if (previous != null) {
                    throw new IllegalArgumentException(
                            "duplicate task id: " + task.getId());
                }
            }

            this.byId = Collections.unmodifiableMap(index);
        }

        Optional<Task> findById(String id) {
            return Optional.ofNullable(byId.get(id));
        }

        List<Task> findAll() {
            return new ArrayList<Task>(byId.values());
        }
    }

    static final class TaskReports {
        private final Clock clock;

        TaskReports(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        LocalDate today() {
            return LocalDate.now(clock);
        }

        Map<Status, Long> countByStatus(List<Task> tasks) {
            return tasks.stream().collect(Collectors.groupingBy(
                    Task::getStatus,
                    () -> new EnumMap<Status, Long>(Status.class),
                    Collectors.counting()));
        }

        Map<Team, Integer> activeMinutesByTeam(List<Task> tasks) {
            return tasks.stream()
                    .filter(Task::isActive)
                    .collect(Collectors.groupingBy(
                            Task::getTeam,
                            () -> new EnumMap<Team, Integer>(Team.class),
                            Collectors.summingInt(
                                    Task::getEstimateMinutes)));
        }

        List<Task> overdue(List<Task> tasks) {
            LocalDate asOf = today();

            Comparator<Task> order = Comparator
                    .comparingInt((Task task) ->
                            task.getPriority().getRank())
                    .thenComparing(Task::getDueDate)
                    .thenComparing(Task::getId);

            return tasks.stream()
                    .filter(task -> task.isOverdue(asOf))
                    .sorted(order)
                    .collect(Collectors.toList());
        }

        Optional<Task> nextUpcoming(List<Task> tasks) {
            LocalDate asOf = today();

            Comparator<Task> order = Comparator
                    .comparing(Task::getDueDate)
                    .thenComparingInt(task ->
                            task.getPriority().getRank())
                    .thenComparing(Task::getId);

            return tasks.stream()
                    .filter(Task::isActive)
                    .filter(task ->
                            !task.getDueDate().isBefore(asOf))
                    .min(order);
        }
    }

    private static String ids(List<Task> tasks) {
        return tasks.stream()
                .map(Task::getId)
                .collect(Collectors.joining(","));
    }

    private static void check(
            boolean condition, String message) {

        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void shutdown(ExecutorService executor) {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(
                    5, TimeUnit.SECONDS)) {

                executor.shutdownNow();
                executor.awaitTermination(
                        5, TimeUnit.SECONDS);
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) {
        LocalDate today = LocalDate.of(2025, 3, 10);

        List<Task> seed = Arrays.asList(
            new Task("T-101", "Add OAuth callback",
                Team.PLATFORM, Status.IN_PROGRESS, Priority.HIGH,
                LocalDate.of(2025, 3, 8), 90),

            new Task("T-102", "Refresh landing page",
                Team.WEB, Status.TODO, Priority.MEDIUM,
                LocalDate.of(2025, 3, 12), 120),

            new Task("T-103", "Write API contract tests",
                Team.QA, Status.TODO, Priority.HIGH,
                LocalDate.of(2025, 3, 9), 60),

            new Task("T-104", "Upgrade build plugin",
                Team.PLATFORM, Status.DONE, Priority.MEDIUM,
                LocalDate.of(2025, 3, 6), 45),

            new Task("T-105", "Review accessibility",
                Team.WEB, Status.IN_PROGRESS, Priority.LOW,
                LocalDate.of(2025, 3, 10), 30),

            new Task("T-106", "Document rollback",
                Team.PLATFORM, Status.TODO, Priority.MEDIUM,
                LocalDate.of(2025, 3, 15), 40),

            new Task("T-107", "Investigate flaky test",
                Team.QA, Status.TODO, Priority.HIGH,
                LocalDate.of(2025, 3, 10), 50)
        );

        TaskRepository repository = new TaskRepository(seed);

        List<Task> tasks = Collections.unmodifiableList(
                repository.findAll());

        TaskReports reports = new TaskReports(
                Clock.fixed(
                    today.atStartOfDay(ZoneOffset.UTC).toInstant(),
                    ZoneOffset.UTC));

        Predicate<Task> urgentActive = Task::isActive;

        urgentActive = urgentActive.and(
                task -> task.getPriority() == Priority.HIGH);

        long urgentCount = tasks.stream()
                .filter(urgentActive)
                .count();

        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Map<Status, Long>> countsFuture =
                    CompletableFuture.supplyAsync(
                            () -> reports.countByStatus(tasks),
                            executor);

            CompletableFuture<String> overdueFuture =
                    CompletableFuture.supplyAsync(
                            () -> reports.overdue(tasks),
                            executor)
                    .thenApply(TaskBoardDemo::ids);

            CompletableFuture.allOf(
                    countsFuture, overdueFuture).join();

            Optional<Task> nextUpcoming =
                    reports.nextUpcoming(tasks);

            Map<Status, Long> counts = countsFuture.join();

            Map<Team, Integer> minutes =
                    reports.activeMinutesByTeam(tasks);

            String overdueIds = overdueFuture.join();

            String nextId = nextUpcoming
                    .map(Task::getId)
                    .orElse("none");

            check(tasks.size() == 7, "task count");

            check(counts.get(Status.TODO) == 4L
                    && counts.get(Status.IN_PROGRESS) == 2L
                    && counts.get(Status.DONE) == 1L,
                    "status counts");

            check(minutes.get(Team.PLATFORM) == 130
                    && minutes.get(Team.WEB) == 150
                    && minutes.get(Team.QA) == 110,
                    "team estimates");

            check("T-101,T-103".equals(overdueIds),
                    "overdue order");

            check("T-107".equals(nextId),
                    "next upcoming task");

            check(urgentCount == 3L,
                    "urgent active count");

            check(!repository.findById("T-999").isPresent(),
                    "missing lookup");

            check(repository.findById("T-101").isPresent(),
                    "existing lookup");

            try {
                new TaskRepository(
                        Arrays.asList(seed.get(0), seed.get(0)));

                throw new AssertionError(
                        "duplicate ID was accepted");

            } catch (IllegalArgumentException expected) {
                // Duplicate IDs are rejected at the repository boundary.
            }

            System.out.println("asOf=" + reports.today());
            System.out.println("taskCount=" + tasks.size());
            System.out.println("countsByStatus=" + counts);
            System.out.println("activeMinutesByTeam=" + minutes);
            System.out.println("overdue=" + overdueIds);
            System.out.println("nextUpcoming=" + nextId);
            System.out.println("urgentActiveCount=" + urgentCount);
            System.out.println("findMissing="
                    + repository.findById("T-999")
                            .map(Task::getTitle)
                            .orElse("not found"));
            System.out.println("checks=PASS");

        } finally {
            shutdown(executor);
        }
    }
}
~~~

## 12. Biên dịch và chạy

### 12.1. Trên JDK 8

Đặt file trong thư mục làm việc rồi chạy:

~~~bash
javac -encoding UTF-8 TaskBoardDemo.java
java TaskBoardDemo
~~~

### 12.2. Trên JDK mới nhưng giữ Java 8 API

~~~bash
javac --release 8 -Xlint:all,-options -encoding UTF-8 TaskBoardDemo.java
java TaskBoardDemo
~~~

`--release 8` được dùng với JDK 9 trở lên. Nếu dùng JDK 8, bỏ `--release` và `-Xlint:all,-options`.

Kiểm tra class file:

~~~bash
javap -verbose TaskBoardDemo
~~~

Tìm dòng:

~~~text
major version: 52
~~~

Major version 52 xác nhận bytecode target Java 8. Khi chạy trên JDK mới hơn, JVM mới vẫn hỗ trợ class file cũ theo nguyên tắc tương thích ngược.

## 13. Kết quả chạy đã xác minh

Stdout từ JDK 24.0.2 sau khi biên dịch bằng `--release 8`:

~~~text
asOf=2025-03-10
taskCount=7
countsByStatus={TODO=4, IN_PROGRESS=2, DONE=1}
activeMinutesByTeam={PLATFORM=130, WEB=150, QA=110}
overdue=T-101,T-103
nextUpcoming=T-107
urgentActiveCount=3
findMissing=not found
checks=PASS
~~~

Giải thích:

- Có 7 task trong repository.
- Trạng thái: 4 TODO, 2 IN_PROGRESS, 1 DONE.
- Thời lượng của task đang hoạt động: PLATFORM 130 phút, WEB 150 phút, QA 110 phút.
- T-101 và T-103 đã quá hạn, đều có priority HIGH; T-101 có due date sớm hơn nên đứng trước.
- Task sắp đến hạn gần nhất là T-107; hai task đến hạn hôm nay được so priority trước, vì vậy HIGH đứng trước LOW.
- Có 3 task vừa active vừa HIGH.
- Tra cứu T-999 trả kết quả vắng mặt và được biểu diễn thành `"not found"`.
- Repository từ chối ID trùng; tất cả assertion đều PASS.

## 14. Vì sao thiết kế này phù hợp với ứng dụng thực tế?

### 14.1. Tách domain, repository và report

- `Task` giữ dữ liệu và invariant.
- `TaskRepository` chịu trách nhiệm tra cứu và uniqueness của ID.
- `TaskReports` chịu trách nhiệm các phép đọc/tổng hợp.
- `main` chỉ lắp ghép dependency và trình bày kết quả.

Cách tách này giúp thay nguồn dữ liệu mà không phải viết lại logic báo cáo. Ví dụ repository sau này có thể đọc từ database, còn `TaskReports` vẫn nhận `List<Task>` hoặc một abstraction tương đương.

### 14.2. Không dùng mutable shared state trong pipeline

Báo cáo không sửa `tasks`, `Task` bất biến và các collector tạo container kết quả riêng. Khi chạy hai báo cáo bằng executor, chúng không cùng ghi vào một `HashMap` hoặc `ArrayList`.

Nếu sau này thêm cache dùng chung, cần xác định ownership, concurrency policy và cách invalidation riêng.

### 14.3. Dùng Clock để test nghiệp vụ ngày tháng

Thay vì mock static `LocalDate.now()`, inject `Clock`. Đây là cách test tự nhiên của `java.time` và cho phép chạy cùng một test ở nhiều ngày khác nhau.

### 14.4. Dùng Comparator với tie-breaker

Thứ tự sắp xếp là một phần của contract báo cáo. Nếu chỉ sort theo priority mà không có tie-breaker, hai task có cùng priority có thể giữ thứ tự theo nguồn. Với API trả top-N hoặc báo cáo có snapshot, nên xác định đầy đủ thứ tự.

### 14.5. Dùng CompletableFuture đúng phạm vi

Hai báo cáo là hai phép đọc độc lập, phù hợp để chạy song song. Nếu tác vụ phụ thuộc kết quả trước, dùng `thenCompose` hoặc `thenApply` phù hợp. Không tạo thread pool mới cho từng task hoặc từng request mà không có kế hoạch quản lý.

Nếu ứng dụng chỉ có một vài phép tính rất nhỏ, chạy tuần tự có thể đơn giản và nhanh hơn do không có overhead scheduling.

## 15. Phân biệt API Java 8 với các API bổ sung về sau

Các tính năng hiện đại sau vẫn hữu ích trên JDK mới nhưng **không nằm trong baseline Java 8**:

| API/tính năng | Có từ | Thay thế/ý nghĩa |
|---|---:|---|
| `var` cho local variables | Java 10 | Local variable type inference |
| `List.of`, `Map.of`, `Set.of` | Java 9 | Factory tạo collection không sửa đổi |
| `Optional.stream()` | Java 9 | Chuyển Optional thành Stream 0/1 phần tử |
| `Stream.takeWhile/dropWhile` | Java 9 | Cắt/bỏ prefix theo Predicate |
| `Collectors.filtering/flatMapping` | Java 9 | Downstream collectors |
| `Collectors.toUnmodifiableList` | Java 10 | Collector tạo List không sửa đổi |
| `record` | Java 16 | Data carrier class ngắn gọn |
| `Stream.toList()` | Java 16 | Kết quả List không sửa đổi |
| `mapMulti` | Java 16 | Một cách flatten dữ liệu trong Stream |
| `ExecutorService` implements `AutoCloseable` | Java 19 | Có thể dùng try-with-resources |
| Pattern matching for `instanceof` | Java 16 | Rút gọn kiểm tra/cast |
| Switch expressions | Java 14 | Switch trả về giá trị |
| Text blocks | Java 15 | Chuỗi nhiều dòng |

Không cần tránh các API mới khi dự án đã nâng baseline. Chỉ cần **không gọi API mới hơn baseline** nếu chương trình phải chạy trên Java 8. Khi nâng runtime, nên nâng từng nhóm API có lợi ích rõ ràng và kiểm tra dependency/test tương ứng.

Ví dụ, trên Java 16+ có thể dùng:

~~~java
List<String> ids = tasks.stream()
        .map(Task::getId)
        .toList();
~~~

Nhưng trên Java 8 phải dùng:

~~~java
List<String> ids = tasks.stream()
        .map(Task::getId)
        .collect(Collectors.toList());
~~~

`Stream.toList()` và `Collectors.toList()` không có cùng guarantee về khả năng sửa đổi. Đừng chỉ thay tên method mà bỏ qua contract collection trả về.

## 16. Các lỗi thường gặp khi kết hợp kỹ thuật Java 8

1. **Gọi `LocalDate.now()` rải rác trong logic.** Khó kiểm thử và có thể đổi ngày giữa pipeline; inject Clock và chụp một ngày cho mỗi báo cáo.
2. **Dùng `Date`/`Calendar` cho logic ngày mới.** Ưu tiên `java.time`; chỉ chuyển đổi với API cũ ở boundary cần interop.
3. **Trả null từ repository.** Dùng `Optional` nếu “không tìm thấy” là một kết quả hợp lệ.
4. **Gọi `Optional.get()` không kiểm tra.** Dùng `orElse`, `orElseGet`, `orElseThrow`, `ifPresent` hoặc `map`.
5. **Dùng Optional làm field cho mọi thuộc tính.** Thường chỉ cần Optional ở return type khi giá trị có thể vắng mặt.
6. **Dùng `ordinal()` làm mã nghiệp vụ của enum.** Thứ tự khai báo enum có thể thay đổi; dùng code/rank tường minh.
7. **Comparator thiếu tie-breaker.** Kết quả top-N có thể khó tái lập.
8. **Comparator dùng phép trừ để so sánh số.** Có thể overflow; dùng `comparingInt`, `comparingLong` hoặc `comparing`.
9. **Dùng Stream như Collection.** Stream là pipeline single-use; terminal operation tiêu thụ stream.
10. **Tái sử dụng cùng một Stream.** Tạo stream mới từ nguồn cho mỗi báo cáo.
11. **Sửa collection nguồn trong `filter` hoặc `map`.** Tránh structural modification khi pipeline đang duyệt.
12. **Dùng side effect trong `forEach` để tích lũy Map/List.** Ưu tiên collector.
13. **Giả định `groupingBy` trả Map có thứ tự cụ thể.** Dùng map factory khi thứ tự là contract.
14. **Dùng `toMap` mà không xử lý key trùng.** Chọn merge function hoặc từ chối dữ liệu trùng theo nghiệp vụ.
15. **Chạy parallel mặc định vì nghĩ luôn nhanh hơn.** Đo workload; chi phí chia/gộp có thể cao hơn lợi ích.
16. **Chia sẻ mutable list/map cho nhiều CompletableFuture.** Dùng input bất biến hoặc cấu trúc concurrent đúng mục đích.
17. **Gọi `supplyAsync` mà không nghĩ về executor.** Overload mặc định dùng common pool; tác vụ blocking có thể ảnh hưởng workload khác.
18. **Quên đóng ExecutorService.** Dùng `shutdown`, `awaitTermination` và `shutdownNow` theo policy.
19. **Nhầm `shutdownNow()` là bảo đảm dừng ngay.** Nó chỉ cố gắng interrupt; task cần hợp tác với interruption.
20. **Dùng `join()` rồi giả định không thể thất bại.** `join` ném `CompletionException` khi stage hoàn tất exceptional.
21. **Gọi `get()`/`join()` quá sớm.** Có thể vô hiệu hóa lợi ích bất đồng bộ; kết hợp stage rồi chờ ở boundary.
22. **Dùng `CompletableFuture` cho mọi phép tính nhỏ.** Chỉ thêm async khi có concurrency hoặc I/O độc lập cần thiết.
23. **Dùng `-source 8 -target 8` mà không giới hạn API.** Ưu tiên `--release 8` khi compiler JDK 9+.
24. **Dùng API Java 9+ trong code Java 8 vì compiler mới vẫn biên dịch.** Kiểm tra bằng `--release 8`.
25. **Nhầm bytecode version với runtime đã được kiểm thử.** Major version 52 xác nhận class file target 8, không chứng minh đã chạy trên mọi JDK vendor/runtime.

## 17. Ma trận kiểm thử nên có

| Case | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| ID hợp lệ | `"T-200"` | Task được tạo |
| ID null/rỗng | `null`, `""`, `"   "` | Constructor từ chối |
| Title rỗng | `" "` | Constructor từ chối |
| Estimate âm | `-1` | Constructor từ chối |
| Ngày đến hạn hôm nay | dueDate = today | Không phải overdue |
| Ngày trước hôm nay | dueDate < today, task active | Overdue |
| Task DONE quá hạn | status DONE | Không được tính overdue |
| Task ID không có | `T-999` | Optional empty |
| Task ID có | `T-101` | Optional present |
| ID trùng | Hai task cùng ID | Repository từ chối |
| Không có task | Danh sách rỗng | Count 0, Optional empty |
| Không có task active | Tất cả DONE | Tổng phút active bằng 0 |
| Hai task cùng priority | Khác dueDate | Ngày sớm hơn đứng trước |
| Hai task cùng dueDate | Khác priority | Priority rank thấp hơn đứng trước |
| Hai task cùng ngày/priority | Khác ID | ID tăng dần đứng trước |
| CompletableFuture lỗi | Supplier ném exception | allOf/join hoàn tất exceptional |
| Executor shutdown | Không còn task chờ | Executor kết thúc |
| Interrupted shutdown | Thread chờ bị interrupt | Shutdown được yêu cầu và interrupt status được giữ |

Trong ứng dụng thực tế, nên tách unit tests cho `Task`, repository và `TaskReports`; kiểm tra `CompletableFuture` riêng bằng executor nhỏ và thời hạn rõ ràng. Không dùng `Thread.sleep` để đồng bộ test khi có thể dùng latch/future.

## 18. Hướng mở rộng từ bài thực hành

Sau khi chạy được bản cơ bản, có thể mở rộng theo từng bước:

1. Thêm `TaskService` để gom các use case tạo, đổi trạng thái và tra cứu.
2. Thêm `TaskRepository` interface và implementation lưu file/database.
3. Thêm bộ lọc theo team, status, priority và khoảng ngày.
4. Thêm thống kê phần trăm hoàn thành bằng `LongSummaryStatistics` hoặc phép tính phù hợp.
5. Thêm lịch sử trạng thái với `Instant` để ghi nhận thời điểm tuyệt đối.
6. Thêm timezone người dùng riêng khi hiển thị deadline.
7. Thêm export CSV bằng `Files.newBufferedWriter` và xử lý encoding/escaping đúng chuẩn CSV.
8. Thêm phân trang nếu dữ liệu lớn thay vì collect toàn bộ kết quả vào memory.
9. Thêm executor riêng cho I/O và CPU nếu có nhiều workload khác nhau.
10. Thêm timeout, retry và error recovery ở các boundary gọi service bên ngoài; không retry mọi lỗi một cách mù quáng.
11. Thêm logging/metrics ở service boundary, tránh log toàn bộ payload nhạy cảm.
12. Nâng baseline lên Java 25 LTS khi dependency và deployment đã sẵn sàng; cân nhắc feature release mới hơn khi tổ chức có quy trình nâng cấp định kỳ.

Không nên thêm database, HTTP client, framework hoặc message broker vào bài cơ bản chỉ để tăng số API. Hãy giữ mỗi phần mở rộng có một yêu cầu nghiệp vụ cụ thể và một cách kiểm thử.

## 19. Checklist hoàn thành

- [ ] Đã chọn rõ JDK runtime mục tiêu và Java API baseline.
- [ ] Đã dùng `--release 8` khi compiler là JDK 9+.
- [ ] Đã kiểm tra bytecode major version 52.
- [ ] Model có invariant và field bất biến.
- [ ] Repository phát hiện duplicate key.
- [ ] Tra cứu vắng mặt dùng Optional.
- [ ] Ngày tháng dùng `java.time`.
- [ ] Clock được inject để test thời gian xác định.
- [ ] Lambda/Predicate mô tả điều kiện nghiệp vụ.
- [ ] Stream không sửa collection nguồn.
- [ ] Collector phù hợp với kiểu kết quả.
- [ ] Comparator có tie-breaker.
- [ ] CompletableFuture có executor phù hợp.
- [ ] Có xử lý exceptional completion ở boundary.
- [ ] Executor được shutdown và chờ kết thúc.
- [ ] Có test empty input, duplicate ID và ngày biên.
- [ ] Không dùng API sau Java 8 trong phần code baseline.
- [ ] Đã ghi rõ JDK thực sự dùng để biên dịch và chạy.

## 20. Bài tập tự thực hành

### Bài 1 — Thêm bộ lọc theo team

Viết method nhận `Team` và trả về task active thuộc team đó. Dùng `filter` và method reference/lambda.

### Bài 2 — Tạo báo cáo priority

Dùng `groupingBy(Task::getPriority, counting())`. Chọn `EnumMap` để thứ tự theo enum.

### Bài 3 — Top 3 task sắp đến hạn

Lọc task active và chưa quá hạn, sort theo dueDate tăng dần, priority rank tăng dần, ID tăng dần rồi `limit(3)`.

### Bài 4 — Tìm task theo ID

Trả `Optional<Task>`. Thử cả ID có và không có, không trả null.

### Bài 5 — Clock test

Chạy cùng một danh sách với hai `Clock.fixed` khác nhau. Quan sát task chuyển từ upcoming sang overdue mà không thay đổi dữ liệu task.

### Bài 6 — Duplicate IDs

Thử tạo repository từ hai task cùng ID. Xác nhận constructor ném `IllegalArgumentException`.

### Bài 7 — CompletableFuture compose

Viết method tìm task rồi gọi một async service lấy chi tiết task. Dùng `thenCompose` để tránh `CompletableFuture<CompletableFuture<T>>`.

### Bài 8 — Error recovery

Thêm một báo cáo có thể thất bại. Thử `exceptionally` để cung cấp fallback có ý nghĩa, đồng thời ghi nhận lỗi; không dùng fallback để che lỗi dữ liệu nghiêm trọng.

### Bài 9 — Executor policy

Thử pool 1 thread và pool 2 threads. Đo thời gian và xác nhận kết quả không đổi. Không kết luận pool lớn luôn nhanh hơn từ dataset nhỏ.

### Bài 10 — Nâng cấp runtime

Biên dịch chương trình bằng JDK mới với `--release 8`, sau đó bỏ `--release` và nâng API baseline có chủ đích. Ghi rõ API nào được thêm và runtime tối thiểu thay đổi ra sao.

## 21. Câu hỏi ôn tập và đáp án

**1. Vì sao bài dùng Java 8 API trên JDK mới?** — Để tận dụng compiler/runtime mới nhưng giữ khả năng tương thích với baseline API Java 8.

**2. JDK 27 và JDK 25 có vai trò gì tại thời điểm bài được biên soạn?** — JDK 27 là feature release mới nhất; JDK 25 là LTS mới nhất theo trang tải JDK Oracle ngày 06/11/2026.

**3. `--release 8` khác `-source 8 -target 8` ở đâu?** — Nó còn giới hạn API platform mà compiler cho phép dùng.

**4. Class file major version 52 tương ứng Java nào?** — Java 8.

**5. Vì sao Task bất biến?** — Giúp chia sẻ an toàn giữa các báo cáo và tránh trạng thái thay đổi giữa lúc xử lý.

**6. Default method trong interface dùng để làm gì?** — Cung cấp implementation mặc định cho method instance.

**7. Static method của interface được gọi thế nào?** — Gọi bằng tên interface, ví dụ `TaskView.hasText`.

**8. `Predicate.and` làm gì?** — Kết hợp hai điều kiện; cả hai phải true.

**9. `Optional` phù hợp ở đâu?** — Return type của thao tác có thể không tìm thấy giá trị.

**10. Vì sao dùng `Clock`?** — Cho phép inject thời gian và test ngày/giờ xác định.

**11. `LocalDate` có timezone không?** — Không; nó chỉ biểu diễn ngày lịch.

**12. `groupingBy` làm gì?** — Nhóm phần tử theo classifier.

**13. Vì sao dùng EnumMap?** — Key là enum, có cấu trúc phù hợp và thứ tự theo enum declaration.

**14. Comparator có tie-breaker để làm gì?** — Tạo thứ tự đầy đủ và kết quả ổn định hơn.

**15. `CompletableFuture.allOf` trả về kết quả các future không?** — Không; nó tạo một future hoàn tất khi tất cả future đầu vào hoàn tất.

**16. Vì sao truyền executor vào `supplyAsync`?** — Kiểm soát thread pool và tách workload khỏi executor mặc định.

**17. `join()` báo lỗi bất đồng bộ thế nào?** — Ném CompletionException nếu stage hoàn tất exceptional.

**18. `shutdown()` có chờ task xong không?** — Không; cần `awaitTermination` nếu muốn chờ.

**19. `shutdownNow()` có bảo đảm dừng ngay task đang chạy không?** — Không; đây là nỗ lực best-effort, task cần hợp tác với interruption.

**20. Có nên dùng `Stream.toList()` trong Java 8 baseline không?** — Không; method này có từ Java 16.

**21. `record` có trong Java 8 không?** — Không; record được hoàn thiện trong Java 16.

**22. Có thể dùng `var` trong source Java 8 không?** — Không; local variable type inference có từ Java 10.

**23. `ExecutorService` có thể dùng try-with-resources trong Java 8 không?** — Không; interface chỉ trở thành AutoCloseable từ Java 19.

**24. Có nên chạy parallel stream mặc định không?** — Không; phải đo workload và đánh giá chi phí chia/gộp.

**25. Vì sao không nên dùng `ordinal()` làm priority rank nghiệp vụ?** — Thứ tự enum có thể thay đổi khi sửa source; rank tường minh biểu đạt policy rõ hơn.

## 22. Tổng kết

Bài tổng hợp cho thấy các kỹ thuật Java 8 vẫn đủ mạnh để xây dựng một ứng dụng nhỏ có cấu trúc tốt trên JDK hiện đại:

- Interface default/static methods dùng để chia sẻ hành vi đúng phạm vi.
- Lambda và functional interfaces mô tả rule lọc.
- Object bất biến và repository giúp kiểm soát dữ liệu.
- `Optional` làm rõ trường hợp không có kết quả.
- `java.time` cùng `Clock` xử lý deadline và giúp test xác định.
- Stream, Collector và Comparator tạo báo cáo có thể đọc và kiểm tra.
- CompletableFuture kết hợp các tác vụ độc lập; ExecutorService quản lý thread lifecycle.

JDK mới cung cấp nhiều cú pháp và API tiện hơn, nhưng một ứng dụng không cần chạy theo mọi tính năng mới. Hãy chọn baseline phù hợp, dùng `--release` để kiểm soát API, nâng cấp có chủ đích và xác minh trên runtime thật của môi trường triển khai.

### Tài liệu chính thức hiện hành

- [Oracle Java Downloads — JDK 27 latest feature release và JDK 25 latest LTS](https://www.oracle.com/java/technologies/downloads/)
- [Oracle Java SE 27 — API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/)
- [Oracle Java SE 27 — Stream API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 27 — Collectors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle Java SE 27 — Comparator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 27 — Optional](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 27 — Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html)
- [Oracle Java SE 27 — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 27 — Functional Interfaces package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/package-summary.html)
- [Oracle Java SE 27 — javac command reference](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Oracle Java SE 27 — Java Language Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/index.html)
