# Kiểm thử handler theo subtype trong Java 21

## 1. Mục tiêu của case study

Trong **Case study command**, một handler thường nhận một kiểu cha chung (ví dụ `Command`) nhưng phải thực hiện **đúng thao tác tương ứng với từng subtype**: tạo yêu cầu, phân công hoặc đóng yêu cầu. Khi dùng **sealed interface**, **record patterns** và **pattern matching for switch** của Java 21, việc dispatch có thể rất rõ ràng. Tuy nhiên, code biên dịch và một vài lệnh chạy thành công **không chứng minh handler đúng với mọi subtype**.

Bài học này tập trung vào **kiểm thử handler theo subtype**: xây một mô hình Command đóng, định nghĩa hợp đồng đầu ra và tác dụng phụ cho từng command, thử các dữ liệu hợp lệ/không hợp lệ, kiểm tra thứ tự sự kiện, khẳng định lệnh bị từ chối không làm đổi trạng thái, rồi xem compiler hỗ trợ kiểm tra đầy đủ subtype như thế nào.

Sau khi học, bạn có thể:

- Thiết kế tập command bằng `sealed interface` và các `record` triển khai; phân biệt subtype dispatch với validation nghiệp vụ.
- Viết `switch (command)` dùng `case OpenTicket(...) when ...` cùng một nhánh fallback **cùng subtype**.
- Viết ma trận test bao phủ từng subtype, guard đúng/sai, root `null`, record component `null`, yêu cầu không tồn tại, trạng thái xung đột và lệnh lặp.
- Kiểm tra cả **kết quả trả về** lẫn **số lượng bản ghi, nội dung bản ghi, event log và việc không có side effect khi lệnh thất bại**.
- Phân biệt **exhaustiveness tại compile time** với **behavioral coverage** của unit tests.
- Dùng một chương trình Java 21 độc lập có assertions và kết quả đã kiểm chứng; chuyển ý tưởng thành JUnit 5 tests trong dự án thực tế.

**Phiên bản:** Java 21. Pattern matching for `switch` và record patterns chính thức từ Java 21 (JEP 441 và JEP 440). Type patterns `instanceof` chính thức từ Java 16 (JEP 394). Ví dụ chạy bằng `javac --release 21`, không cần bật preview.

## 2. Mô hình: một handler, ba subtype của Command

Trong ứng dụng quản lý ticket giả lập, ta nhận ba lệnh:

```java
sealed interface Command permits OpenTicket, AssignTicket, CloseTicket {}

record OpenTicket(String id, String title) implements Command {}
record AssignTicket(String id, String owner) implements Command {}
record CloseTicket(String id) implements Command {}
```

Đây là **khai báo minh họa**, được định nghĩa bên trong lớp hoàn chỉnh ở mục 6.

Mỗi subtype có một ý định riêng:

| Subtype command | Dữ liệu đầu vào | Thao tác thành công | Các trường hợp từ chối |
|---|---|---|---|
| `OpenTicket` | ID, title | Tạo ticket mới, ghi một event `OPEN` | Thiếu ID/title; ID đã tồn tại |
| `AssignTicket` | ID, owner | Gán owner cho ticket chưa đóng, ghi một event `ASSIGN` | Thiếu ID/owner; ticket chưa tồn tại; ticket đã đóng |
| `CloseTicket` | ID | Chuyển ticket sang closed, ghi một event `CLOSE` | Thiếu ID; ticket chưa tồn tại; ticket đã đóng |
| `null` | Không có command | Không thực thi thao tác nào | Trả mã `REJECTED:NULL_COMMAND` |

Một ticket được lưu trong mô hình:

```java
record Ticket(String title, String owner, boolean closed) {}
```

**Hợp đồng state:** `open` tạo Ticket(title, null, false); `assign` tạo bản record Ticket mới giữ title và `closed=false` nhưng cập nhật owner; `close` tạo record mới giữ title/owner và đặt `closed=true`.

**Hợp đồng event:** chỉ những command **được xử lý thành công và có thay đổi state** mới thêm một event. Những command bị từ chối vì validation, không tìm thấy hoặc conflict **không** thêm event và **không** thay state.

**Đây là chính sách dạy học**, không phải API chuẩn của Java hay quy tắc bắt buộc cho hệ thống ticket thật. Ví dụ này cho phép reassign ticket đang mở; hệ thống thật có thể yêu cầu kiểm tra quyền truy cập, idempotency key, transaction và concurrency riêng.

## 3. Dispatch theo subtype khác với kiểm tra điều kiện nghiệp vụ

Trong Java 21, một handler có thể dùng:

```java
String handle(Command command) {
    return switch (command) {
        case null -> "REJECTED:NULL_COMMAND";

        case OpenTicket(var id, var title)
                when hasText(id) && hasText(title) -> open(id, title);
        case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";

        case AssignTicket(var id, var owner)
                when hasText(id) && hasText(owner) -> assign(id, owner);
        case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";

        case CloseTicket(var id) when hasText(id) -> close(id);
        case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
    };
}
```

Đoạn trên là **thân phương thức minh họa**, với các helper `hasText`, `open`, `assign`, `close` được định nghĩa ở chương trình đầy đủ.

Có ba tầng trách nhiệm:

1. **Subtype dispatch:** `case OpenTicket(...)`, `case AssignTicket(...)`, `case CloseTicket(...)` chọn loại command dựa trên kiểu runtime và record structure.
2. **Input validation:** `when hasText(...)` quyết định command của subtype đó đủ dữ liệu tối thiểu hay không.
3. **Domain operation:** `open/assign/close` kiểm tra trạng thái repository hiện tại rồi quyết định kết quả và side effects.

Điều quan trọng: `when` **không biến command thành subtype mới**. Ví dụ một `OpenTicket(null, "Bug")` vẫn là `OpenTicket`, nhưng guard không thỏa. Nhờ nhánh `case OpenTicket ignored` đứng sau, handler trả `REJECTED:OPEN_FIELDS` thay vì bỏ qua input.

Nếu dùng nhiều nhánh `case` trong cùng subtype, phải **đặt nhánh có guard trước nhánh tổng quát**. Nhánh tổng quát đặt ở trên có thể làm nhánh hẹp bên dưới bị compiler bác bỏ vì *dominated*.

### 3.1. Vì sao `var` quan trọng khi có component null?

Record patterns dùng `var id`, `var title` trực tiếp trên các component tham chiếu. Dù `id == null` hay `title == null`, record `OpenTicket` vẫn có thể khớp và bind các biến đó. Guard `hasText` sau đó trả false.

Với helper:

```java
static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

`&&` đánh giá từ trái sang phải. `value.isBlank()` chỉ được gọi sau khi giá trị khác null, nên command với field null không gây `NullPointerException`.

Một **null ở root** thì khác: `switch` nhận selector null sẽ được `case null` xử lý. Không nên kỳ vọng `default` thông thường tự bắt null; trong các pattern switch Java 21, phải khai báo chính sách null riêng nếu muốn trả về chuỗi thay vì ném exception.

## 4. Ma trận test phải được xây từ subtype và trạng thái

Chỉ test một command mỗi loại ở “happy path” là chưa đủ. Một ma trận hữu ích có hai chiều: **command subtype** và **điều kiện hiện tại của repository**.

| Nhóm | Test case | Kết quả mong đợi | Có thay đổi state/event? |
|---|---|---|---|
| Null root | `handle(null)` | `REJECTED:NULL_COMMAND` | Không |
| Open — dữ liệu thiếu | ID null hoặc title trắng | `REJECTED:OPEN_FIELDS` | Không |
| Open — thành công | Tạo T1 lần đầu | `OPENED:T1` | Có: thêm ticket và event |
| Open — trùng ID | Tạo T1 lần hai | `CONFLICT:DUPLICATE:T1` | Không |
| Assign — dữ liệu thiếu | Owner null hoặc ID rỗng | `REJECTED:ASSIGN_FIELDS` | Không |
| Assign — không tìm thấy | Gán T9 | `NOT_FOUND:T9` | Không |
| Assign — thành công | Gán T1 cho Ana | `ASSIGNED:T1` | Có: thay owner và ghi event |
| Assign — gán lại | Gán T1 cho Ben | `ASSIGNED:T1` | Có: owner mới, event mới |
| Assign — ticket đã đóng | Gán T1 sau khi close | `CONFLICT:CLOSED:T1` | Không |
| Close — dữ liệu thiếu | ID null | `REJECTED:CLOSE_FIELDS` | Không |
| Close — không tìm thấy | Đóng T9 | `NOT_FOUND:T9` | Không |
| Close — thành công | Đóng T1 | `CLOSED:T1` | Có: closed=true, event |
| Close — lặp | Đóng T1 lần nữa | `CONFLICT:ALREADY_CLOSED:T1` | Không |

Phần lớn lỗi dispatch không nằm ở việc `case OpenTicket` không được chọn, mà ở việc command **đúng kiểu nhưng guard false hoặc domain state không cho phép**. Khi test, hãy đặt tên case sao cho reviewer biết mình đang xác minh loại nào.

### 4.1. Test command theo từng subtype

Với mỗi subtype, nên có ít nhất:

- **Một happy path** để xác nhận case được chọn và operation đúng.
- **Một invalid input** để xác nhận guarded case bị bỏ qua nhưng fallback cùng subtype được chọn.
- **Một lỗi domain state** nếu operation phụ thuộc repository.
- **Một test side-effect**: command không thành công không được âm thầm thay dữ liệu hoặc ghi audit.
- **Một test biên** cho field rỗng, blank, null hay trạng thái lặp, tùy hợp đồng của subtype.

Subtype coverage **không đồng nghĩa branch coverage**. Một test OpenTicket thành công chưa bao phủ được nhánh validation và duplicate. Một test AssignTicket thành công chưa bảo đảm đóng ticket xong sẽ bị từ chối gán tiếp.

### 4.2. Test trạng thái trước và sau

Nếu chỉ viết:

```java
assertEquals("ASSIGNED:T1", handler.handle(new AssignTicket("T1", "Ana")));
```

thì test có thể pass dù handler **không cập nhật owner** hoặc thêm hai event. Vì vậy cần kiểm tra Ticket thật được lưu và event history.

Ngược lại, một command thất bại có thể trả đúng mã lỗi nhưng vẫn vô tình gọi `tickets.put(...)` hoặc ghi một event trước khi return. Bởi thế nên lưu **snapshot state trước khi gọi** và đối chiếu sau khi gọi.

## 5. Thiết kế fake repository để test không phụ thuộc I/O

Ví dụ dùng một handler với:

```java
private final Map<String, Ticket> tickets = new HashMap<>();
private final List<String> events = new ArrayList<>();
```

Lợi ích:

- Không cần database, message broker, HTTP server hoặc transaction manager.
- Có thể kiểm tra trực tiếp số ticket, nội dung record, số event và thứ tự event.
- Test chạy nhanh, có thể tái lập trên máy local/CI.
- Mọi state của ví dụ đều nằm trong cùng một đối tượng Handler, nên dễ theo dõi chuỗi command.

**Giới hạn:** một fake in-memory không chứng minh database transaction, isolation, retry, đồng bộ đa luồng, hoặc thứ tự publish thực tế. Sau unit test cần thêm integration/contract tests cho repository và messaging adapter của hệ thống thật.

Nếu code production đã dùng interface như `TicketRepository` và `EventPublisher`, hãy inject fake implementations thay vì nhúng `HashMap` vào handler production. Ví dụ ở bài gom tất cả vào một lớp để có **một file Java tự chạy**; đây là lựa chọn phục vụ học tập.

## 6. Chương trình Java 21 đầy đủ đã biên dịch và chạy

Lưu mã sau vào **`SubtypeHandlerTestDemo.java`**. Chương trình không phụ thuộc JUnit hay thư viện ngoài. Nó kiểm tra 17 lượt gọi handler bằng expected output, số ticket, số event và thay đổi state; ngoài ra còn xác minh nội dung Ticket và thứ tự toàn bộ event cuối cùng.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class SubtypeHandlerTestDemo {
    sealed interface Command permits OpenTicket, AssignTicket, CloseTicket {}
    record OpenTicket(String id, String title) implements Command {}
    record AssignTicket(String id, String owner) implements Command {}
    record CloseTicket(String id) implements Command {}
    record Ticket(String title, String owner, boolean closed) {}

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static final class Handler {
        private final Map<String, Ticket> tickets = new HashMap<>();
        private final List<String> events = new ArrayList<>();

        String handle(Command command) {
            return switch (command) {
                case null -> "REJECTED:NULL_COMMAND";
                case OpenTicket(var id, var title)
                        when hasText(id) && hasText(title) -> open(id, title);
                case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";
                case AssignTicket(var id, var owner)
                        when hasText(id) && hasText(owner) -> assign(id, owner);
                case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";
                case CloseTicket(var id) when hasText(id) -> close(id);
                case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
            };
        }

        private String open(String id, String title) {
            if (tickets.containsKey(id)) return "CONFLICT:DUPLICATE:" + id;
            tickets.put(id, new Ticket(title, null, false));
            events.add("OPEN:" + id);
            return "OPENED:" + id;
        }

        private String assign(String id, String owner) {
            Ticket current = tickets.get(id);
            if (current == null) return "NOT_FOUND:" + id;
            if (current.closed()) return "CONFLICT:CLOSED:" + id;
            tickets.put(id, new Ticket(current.title(), owner, false));
            events.add("ASSIGN:" + id + ":" + owner);
            return "ASSIGNED:" + id;
        }

        private String close(String id) {
            Ticket current = tickets.get(id);
            if (current == null) return "NOT_FOUND:" + id;
            if (current.closed()) return "CONFLICT:ALREADY_CLOSED:" + id;
            tickets.put(id, new Ticket(current.title(), current.owner(), true));
            events.add("CLOSE:" + id);
            return "CLOSED:" + id;
        }
    }

    static void expect(String label, Handler handler, Command command,
                       String expectedResult, int expectedCount, int expectedEvents,
                       boolean expectedMutation) {
        Map<String, Ticket> before = new HashMap<>(handler.tickets);
        List<String> auditBefore = new ArrayList<>(handler.events);
        String result = handler.handle(command);
        boolean mutated = !before.equals(handler.tickets)
                || !auditBefore.equals(handler.events);
        if (!Objects.equals(expectedResult, result)
                || handler.tickets.size() != expectedCount
                || handler.events.size() != expectedEvents
                || mutated != expectedMutation) {
            throw new AssertionError(label + ": " + result
                    + " count=" + handler.tickets.size()
                    + " events=" + handler.events.size()
                    + " mutated=" + mutated);
        }
        System.out.println(label + " => " + result + " | mutated=" + mutated);
    }

    static void ticketEquals(Handler handler, String id, Ticket expected) {
        if (!Objects.equals(expected, handler.tickets.get(id))) {
            throw new AssertionError("ticket state mismatch for " + id);
        }
    }

    static void auditEquals(Handler handler, String... expected) {
        if (!handler.events.equals(List.of(expected))) {
            throw new AssertionError("event log mismatch: " + handler.events);
        }
    }

    public static void main(String[] args) {
        Handler handler = new Handler();
        expect("null command", handler, null, "REJECTED:NULL_COMMAND", 0, 0, false);
        expect("open null id", handler, new OpenTicket(null, "Bug"),
                "REJECTED:OPEN_FIELDS", 0, 0, false);
        expect("open blank title", handler, new OpenTicket("T1", " "),
                "REJECTED:OPEN_FIELDS", 0, 0, false);
        expect("open T1", handler, new OpenTicket("T1", "Bug"),
                "OPENED:T1", 1, 1, true);
        ticketEquals(handler, "T1", new Ticket("Bug", null, false));
        expect("duplicate T1", handler, new OpenTicket("T1", "Another"),
                "CONFLICT:DUPLICATE:T1", 1, 1, false);
        expect("open T2", handler, new OpenTicket("T2", "Feature"),
                "OPENED:T2", 2, 2, true);

        expect("assign null owner", handler, new AssignTicket("T1", null),
                "REJECTED:ASSIGN_FIELDS", 2, 2, false);
        expect("assign blank id", handler, new AssignTicket("", "Ana"),
                "REJECTED:ASSIGN_FIELDS", 2, 2, false);
        expect("assign absent", handler, new AssignTicket("T9", "Ana"),
                "NOT_FOUND:T9", 2, 2, false);
        expect("assign T1", handler, new AssignTicket("T1", "Ana"),
                "ASSIGNED:T1", 2, 3, true);
        ticketEquals(handler, "T1", new Ticket("Bug", "Ana", false));
        expect("reassign T1", handler, new AssignTicket("T1", "Ben"),
                "ASSIGNED:T1", 2, 4, true);
        ticketEquals(handler, "T1", new Ticket("Bug", "Ben", false));

        expect("close null id", handler, new CloseTicket(null),
                "REJECTED:CLOSE_FIELDS", 2, 4, false);
        expect("close absent", handler, new CloseTicket("T9"),
                "NOT_FOUND:T9", 2, 4, false);
        expect("close T1", handler, new CloseTicket("T1"),
                "CLOSED:T1", 2, 5, true);
        ticketEquals(handler, "T1", new Ticket("Bug", "Ben", true));
        expect("close T1 twice", handler, new CloseTicket("T1"),
                "CONFLICT:ALREADY_CLOSED:T1", 2, 5, false);
        expect("assign closed", handler, new AssignTicket("T1", "Ana"),
                "CONFLICT:CLOSED:T1", 2, 5, false);
        expect("close T2", handler, new CloseTicket("T2"),
                "CLOSED:T2", 2, 6, true);
        ticketEquals(handler, "T2", new Ticket("Feature", null, true));

        auditEquals(handler, "OPEN:T1", "OPEN:T2", "ASSIGN:T1:Ana",
                "ASSIGN:T1:Ben", "CLOSE:T1", "CLOSE:T2");
        System.out.println("audit => 6 events in expected order");
    }
}
```

### Biên dịch và chạy

Trên JDK 21 hoặc cao hơn:

```bash
javac --release 21 SubtypeHandlerTestDemo.java
java SubtypeHandlerTestDemo
```

**Stdout thực tế đã được kiểm chứng:**

```text
null command => REJECTED:NULL_COMMAND | mutated=false
open null id => REJECTED:OPEN_FIELDS | mutated=false
open blank title => REJECTED:OPEN_FIELDS | mutated=false
open T1 => OPENED:T1 | mutated=true
duplicate T1 => CONFLICT:DUPLICATE:T1 | mutated=false
open T2 => OPENED:T2 | mutated=true
assign null owner => REJECTED:ASSIGN_FIELDS | mutated=false
assign blank id => REJECTED:ASSIGN_FIELDS | mutated=false
assign absent => NOT_FOUND:T9 | mutated=false
assign T1 => ASSIGNED:T1 | mutated=true
reassign T1 => ASSIGNED:T1 | mutated=true
close null id => REJECTED:CLOSE_FIELDS | mutated=false
close absent => NOT_FOUND:T9 | mutated=false
close T1 => CLOSED:T1 | mutated=true
close T1 twice => CONFLICT:ALREADY_CLOSED:T1 | mutated=false
assign closed => CONFLICT:CLOSED:T1 | mutated=false
close T2 => CLOSED:T2 | mutated=true
audit => 6 events in expected order
```

Có **17 tình huống lệnh** và một xác minh cuối về toàn bộ event history. Chương trình tự ném `AssertionError` nếu kết quả trả về, kích thước repository, số event, cờ mutation hoặc snapshot cụ thể sai. Việc in đủ 18 dòng nói trên chỉ xảy ra khi tất cả assertions đã qua.

**Phạm vi chứng minh:** Bộ test này cho thấy logic của ví dụ đúng với dữ liệu đã thử và bằng chứng về side effects trong fake store. Nó **không** chứng minh handler production sẽ an toàn dưới giao dịch database, mạng, bất đồng bộ hoặc cạnh tranh đa luồng.

## 7. Phân tích kết quả theo subtype

### 7.1. OpenTicket: validation, thành công và duplicate

Ba đường đi chính:

```java
case OpenTicket(var id, var title)
        when hasText(id) && hasText(title) -> open(id, title);
case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";
```

- `new OpenTicket(null, "Bug")` vẫn là một OpenTicket và record pattern nhận các component, nhưng `hasText(id)` false, nên fallback trả `REJECTED:OPEN_FIELDS`. Không có thay đổi state/event.
- `new OpenTicket("T1", " ")` có title blank: `hasText(title)` false, fallback cũng được chọn.
- `new OpenTicket("T1", "Bug")` hợp lệ: guard true, `open` tạo ticket và ghi một event OPEN.
- Lệnh OpenTicket cùng ID nhưng title khác **không** ghi đè ticket cũ: domain operation trả `CONFLICT:DUPLICATE:T1` và cờ `mutated=false`.

Test không chỉ khẳng định chuỗi `OPENED:T1` mà còn kiểm tra ticket thật là `Ticket("Bug", null, false)`. Nếu handler thêm event nhưng quên cập nhật map, hoặc cập nhật map sai title, test sẽ thất bại.

### 7.2. AssignTicket: validation, missing, update, closed

Nhánh:

```java
case AssignTicket(var id, var owner)
        when hasText(id) && hasText(owner) -> assign(id, owner);
case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";
```

Khi ID hay owner không hợp lệ, handler **không gọi** phương thức `assign`. Với ID hợp lệ nhưng chưa có ticket, phương thức vẫn chạy và trả `NOT_FOUND:T9` không side effect.

Khi ticket T1 đang mở:

1. Gán cho Ana → Ticket title không đổi, owner="Ana", closed=false và thêm event.
2. Gán lại cho Ben → Ticket owner="Ben", giữ title và closed=false; thêm một event mới.

Khi Ticket T1 đã đóng, lệnh AssignTicket hợp lệ về mặt cú pháp/field nhưng **không hợp lệ về trạng thái domain**. Kết quả là `CONFLICT:CLOSED:T1`, không được đổi owner hoặc ghi event. Đây là khác biệt quan trọng giữa **guard match** và **business rule**.

### 7.3. CloseTicket: missing, success, repeated

Nhánh:

```java
case CloseTicket(var id) when hasText(id) -> close(id);
case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
```

- ID null → fallback dữ liệu thiếu.
- ID T9 chưa tồn tại → `NOT_FOUND:T9`.
- ID T1 đang mở → chuyển sang closed=true, ghi `CLOSE:T1`.
- ID T1 đã closed → `CONFLICT:ALREADY_CLOSED:T1`, không ghi event trùng.
- ID T2 đang mở → đóng thành công, giữ owner null nếu ticket chưa từng được assign.

Test “close twice” chứng minh một chính sách **không idempotent về result label**: lần thứ hai trả conflict, không phải CLOSED lần nữa. Tuy nhiên về **state effect**, lệnh lặp không làm thay đổi dữ liệu. Một API production có thể chọn trả “already closed” như thành công idempotent; điều quan trọng là thiết lập hợp đồng rõ và test theo hợp đồng đó.

### 7.4. Null command

`case null -> "REJECTED:NULL_COMMAND";` là đường đi rõ ràng. Trong pattern switch Java 21, một `default` chung thông thường **không tự bắt selector null**. Không được cho rằng handler có thể bỏ `case null` mà vẫn trả mã lỗi như trên.

## 8. Vì sao kiểm tra tác dụng phụ quan trọng ngang output?

Trong chương trình, phương thức `expect(...)` sao chép map và event list trước mỗi lượt gọi:

```java
Map<String, Ticket> before = new HashMap<>(handler.tickets);
List<String> auditBefore = new ArrayList<>(handler.events);
String result = handler.handle(command);
boolean mutated = !before.equals(handler.tickets)
        || !auditBefore.equals(handler.events);
```

Cờ `mutated` giúp chứng minh khi command bị từ chối, fake store và event history không đổi. Nhưng cờ này **chỉ có thể nói “có một sự khác biệt quan sát được”**; vì vậy chương trình còn kiểm tra số lượng, expected result, snapshot từng Ticket quan trọng và toàn bộ event sequence cuối cùng.

Ví dụ một bug có thể “gán nhầm T2 thay vì T1”, map vẫn có số lượng 2 và event count vẫn tăng 1. Nếu test chỉ xét count, lỗi có thể bị bỏ sót. Test snapshot `Ticket("Bug","Ana",false)` cho T1 và thứ tự event giúp phát hiện nhiều dạng sai lệch hơn.

Trong ứng dụng dùng mock:

- Dùng **fake repository** khi cần kiểm tra state sau một chuỗi thao tác.
- Dùng **mock/spy port** khi muốn xác nhận một lệnh gọi external dependency xảy ra đúng một lần hoặc không xảy ra.
- Nếu handler publish sự kiện sau commit, cần integration test về transaction boundary, không chỉ kiểm tra danh sách giả lập.
- Nếu handler có clock, UUID, network, inject các dependency đó để test xác định và tái lập.

**Đừng xem “không thay state ở cuối” là bằng chứng tuyệt đối “không có side effect”.** Một handler có thể đã gọi external service rồi rollback local map. Trong bài này, mọi side effect được quan sát đều nằm trong map/list nên snapshot có ý nghĩa. Với production, phải xét thêm các side-effect ports.

## 9. JUnit 5: tách test theo trách nhiệm thay vì chỉ chạy main

Chương trình mục 6 tự đủ để compile bằng JDK. Khi đưa vào dự án, có thể viết test class riêng dùng **JUnit Jupiter 5** (cần dependency trong Maven/Gradle). Ví dụ trong **cùng package** với `SubtypeHandlerTestDemo`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SubtypeHandlerJUnitTests {
    @Test
    void openTicketCreatesExactlyOneTicket() {
        var handler = new SubtypeHandlerTestDemo.Handler();

        assertEquals("OPENED:T1",
                handler.handle(new SubtypeHandlerTestDemo.OpenTicket("T1", "Bug")));

        SubtypeHandlerTestDemo.ticketEquals(
                handler, "T1", new SubtypeHandlerTestDemo.Ticket("Bug", null, false));
        SubtypeHandlerTestDemo.auditEquals(handler, "OPEN:T1");
    }

    @Test
    void assignUnknownTicketDoesNotProduceEvent() {
        var handler = new SubtypeHandlerTestDemo.Handler();

        assertEquals("NOT_FOUND:T9",
                handler.handle(new SubtypeHandlerTestDemo.AssignTicket("T9", "Ana")));

        SubtypeHandlerTestDemo.auditEquals(handler);
    }

    @Test
    void invalidOpenIsRejectedBySubtypeFallback() {
        var handler = new SubtypeHandlerTestDemo.Handler();

        assertEquals("REJECTED:OPEN_FIELDS",
                handler.handle(new SubtypeHandlerTestDemo.OpenTicket(null, "Bug")));
        SubtypeHandlerTestDemo.auditEquals(handler);
    }
}
```

Đây là **mẫu JUnit bổ sung**, không phải phần đã biên dịch bằng `javac --release 21` đơn thuần. Để chạy cần JUnit Jupiter 5, runner tương ứng và một cấu trúc package phù hợp. Nếu đặt class main vào package có tên, lớp test phải nằm cùng package (hoặc thay đổi visibility một cách có chủ đích).

**Cách tổ chức test tốt hơn khi dự án phát triển:**

- Mỗi subtype có một nhóm unit tests: `OpenTicketHandlerTest`, `AssignTicketHandlerTest`, `CloseTicketHandlerTest` hoặc nhóm `@Nested` trong một class.
- Dùng `@ParameterizedTest` khi có nhiều biến thể cùng một quy tắc (ví dụ trường null, rỗng, chỉ whitespace), nhưng **không gom mọi subtype vào một expected giống nhau** nếu hợp đồng khác.
- Mỗi test nên tạo **Handler mới** hoặc dựng fake repository theo dữ liệu fixture xác định, tránh phụ thuộc thứ tự thực thi JUnit.
- Khi cần test chuỗi trạng thái như open → assign → close, cho chuỗi đó nằm **trong cùng một test rõ nghĩa**, chứ không dùng một test mở để chuẩn bị state cho test đóng.
- Kiểm tra cả command result và state/event assertions; tách assertions lỗi validation, conflict, not-found để khi fail biết ngay nguyên nhân.

### Ma trận JUnit đề xuất

| Nhóm test | Test tiêu biểu | Loại assertion |
|---|---|---|
| `OpenTicket` valid | Tạo ticket mới | Result, ticket snapshot, event |
| `OpenTicket` invalid | ID null/title blank | Result, state unchanged, no event |
| `OpenTicket` duplicate | ID đã có | Conflict, không ghi đè, không event |
| `AssignTicket` valid | Update owner | Result, owner mới, event đúng |
| `AssignTicket` not found | ID chưa có | Not found, không state/event |
| `AssignTicket` closed | Assign ticket đã đóng | Conflict, state/event giữ nguyên |
| `CloseTicket` valid | Đóng ticket | Result, closed=true, event |
| `CloseTicket` repeated | Đóng lần hai | Conflict, không event trùng |
| Null command | `handle(null)` | Result, no side effect |
| Workflow | Open → Assign → Close | State và event order xuyên suốt |

**Compiler không biết** Test A cần kiểm tra event, còn Test B cần kiểm tra không có event. Đây là nghĩa vụ của test contract.

## 10. Exhaustiveness: compiler kiểm tra các subtype, test kiểm tra hành vi

### 10.1. Thiết kế sealed giúp phát hiện thiếu handler mới

Với:

```java
sealed interface Command permits OpenTicket, AssignTicket, CloseTicket {}
```

và `switch expression` xử lý mọi subtype bằng một nhánh fallback không guard của đúng subtype:

```java
case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";
case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";
case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
```

compiler có thể chứng minh các command không null đều có nhánh phù hợp. Nếu ứng dụng thêm `ReopenTicket` vào `permits` nhưng không thêm case cho subtype này, build sẽ báo thiếu exhaustiveness. Đây là một **lợi ích của việc không thêm `default` vô cớ**.

**Không nhầm:** exhaustiveness chỉ chứng minh mọi subtype có đường đi. Nó không chứng minh OpenTicket chắc chắn tạo record, AssignTicket chắc chắn cập nhật owner, hay CloseTicket chắc chắn phát event đúng. Những điều đó phải được test.

### 10.2. Ví dụ compiler từ chối thiếu subtype

Tệp độc lập **`MissingSubtypeCase.java`** sau đây **cố ý không biên dịch**:

```java
public class MissingSubtypeCase {
    sealed interface Command permits Open, Close, Retry {}
    record Open() implements Command {}
    record Close() implements Command {}
    record Retry() implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Open open -> "OPEN";
            case Close close -> "CLOSE";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 MissingSubtypeCase.java
```

Compiler từ chối vì `Retry` chưa được bao phủ trong `switch expression`. Đây là hành vi được kiểm tra thực tế bằng `javac --release 21`.

Nếu thay bằng `default -> "IGNORED";`, mã có thể biên dịch mà không buộc đội ngũ xác định semantics cho Retry mới. Với command domain đóng, đây là rủi ro: một subtype mới bị “nuốt” mà không báo lỗi build.

### 10.3. Ví dụ compiler từ chối nhánh bị dominated

Tệp độc lập **`DominatedSubtypeCase.java`** cũng **cố ý không biên dịch**:

```java
public class DominatedSubtypeCase {
    sealed interface Command permits Open, Close {}
    record Open() implements Command {}
    record Close() implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Command any -> "ANY";
            case Open open -> "OPEN";
            case Close close -> "CLOSE";
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 DominatedSubtypeCase.java
```

`case Command any` bao phủ mọi command khác null, khiến hai nhánh subtype phía sau bị **dominated**. `javac` đã được kiểm tra và từ chối các nhánh này. Sửa bằng cách đưa case cho subtype cụ thể lên trước (hoặc bỏ nhánh rộng khi sealed hierarchy đã được bao phủ đầy đủ).

### 10.4. Thêm subtype là một yêu cầu test mới

Khi thêm một command record:

```java
record ReopenTicket(String id) implements Command {}
```

ngoài việc cập nhật `permits` và `switch`, hãy thêm **test riêng** cho happy path, validation, lỗi domain state, side effects và thứ tự event của `ReopenTicket`. Compiler chỉ nhắc thiếu `case`; nó **không sinh hộ test**.

## 11. Sự khác biệt giữa match, guard và domain failure

Đây là phân tách quan trọng nhất khi test handler:

| Đầu vào | Pattern subtype có khớp? | Guard hợp lệ? | Operation được gọi? | Kết quả |
|---|---|---|---|---|
| `new OpenTicket(null,"Bug")` | Có | Không | Không | `REJECTED:OPEN_FIELDS` |
| `new OpenTicket("T1","Bug")` lần đầu | Có | Có | Có | `OPENED:T1` |
| `new OpenTicket("T1","Other")` khi T1 đã có | Có | Có | Có | `CONFLICT:DUPLICATE:T1` |
| `new AssignTicket("T9","Ana")` | Có | Có | Có | `NOT_FOUND:T9` |
| `new AssignTicket("T1","Ana")` khi T1 đã đóng | Có | Có | Có | `CONFLICT:CLOSED:T1` |
| `new CloseTicket(null)` | Có | Không | Không | `REJECTED:CLOSE_FIELDS` |
| `new CloseTicket("T1")` khi đang mở | Có | Có | Có | `CLOSED:T1` |
| `new CloseTicket("T1")` lần hai | Có | Có | Có | `CONFLICT:ALREADY_CLOSED:T1` |
| `null` | Không phải subtype | Không đánh giá | Không | `REJECTED:NULL_COMMAND` |

Suy luận từ bảng:

- **“Pattern không match”** khác **“pattern match nhưng guard false”**.
- **“Guard true”** khác **“command được chấp nhận ở domain state hiện tại”**.
- **“Handler trả mã thành công”** khác **“state/event đúng sau khi xử lý”**.

Khi viết test theo subtype, hãy làm rõ bạn muốn bảo vệ tầng nào. Các lỗi từ ba tầng này nên được đặt tên khác nhau trong test để chẩn đoán nhanh hơn.

## 12. Các lỗi phổ biến khi kiểm thử handler theo subtype

### 12.1. Chỉ kiểm tra giá trị trả về

Test `assertEquals("CLOSED:T1", handle(...))` không phát hiện quên đặt `closed=true`. Kiểm tra record cuối cùng và event tương ứng.

### 12.2. Chỉ kiểm tra số lượng event

Hai lần publish sự kiện sai thứ tự có thể vẫn có count đúng. Kiểm tra **nội dung và thứ tự** event; trong ví dụ, chuỗi mong đợi là `OPEN:T1` → `OPEN:T2` → `ASSIGN:T1:Ana` → `ASSIGN:T1:Ben` → `CLOSE:T1` → `CLOSE:T2`.

### 12.3. Test failure sau khi state đã bị sửa ngầm

Một handler có thể cập nhật map rồi mới phát hiện duplicate/conflict. Test cần chứng minh state **không đổi** ở mọi nhánh fail, không chỉ mã lỗi giống expected.

### 12.4. Bỏ qua null và blank

`OpenTicket(null,"Bug")` vẫn là đúng subtype nhưng không đủ điều kiện input. Nếu `when` gọi `id.isBlank()` trước khi kiểm tra null, một component null có thể ném exception. Test cần cả null và chuỗi whitespace.

### 12.5. Test subtype bằng class name string

Không cần viết logic như `command.getClass().getSimpleName().equals("OpenTicket")` để xác nhận dispatch. Nó dễ vỡ khi đổi tên/refactor. Dùng đúng instance subtype và expected behavior; compiler giúp kiểm tra kiểu.

### 12.6. Dùng default để “bảo đảm luôn xử lý”

Trong sealed hierarchy, `default` có thể che thiếu xử lý subtype mới. Nếu domain command cố tình đóng, nên tận dụng exhaustive switch. Nếu command là tập kiểu mở, cần fallback có chính sách rõ và test fallback đó.

### 12.7. Đặt case tổng quát trước case cụ thể

`case Command c` đứng trước `case OpenTicket o` làm case hẹp bị dominated và compiler từ chối. Test runtime không thể chữa lỗi compile-time.

### 12.8. Trộn test của nhiều subtype vào một assertion mơ hồ

Một test khổng lồ “all commands work” với cùng expected cho mọi subtype khó tìm nguyên nhân khi fail. Dùng test chuyên biệt, đặt tên mô tả trạng thái, và chỉ ghép workflow khi thật sự muốn kiểm tra tương tác giữa các lệnh.

### 12.9. Để tests phụ thuộc thứ tự chạy JUnit

Nếu một test OpenTicket chạy trước và tạo fixture cho test AssignTicket trong một shared handler, kết quả sẽ không ổn định khi JUnit chạy lại hoặc song song. Mỗi test nên tạo fixture riêng. Ví dụ main ở mục 6 là **một workflow tuần tự có chủ đích**, không phải mẫu để nhiều test tự phụ thuộc nhau.

### 12.10. Bỏ qua concurrency và transaction

Fake Map không mô phỏng hai luồng cùng OpenTicket một ID. Kiểm tra `containsKey` rồi `put` trong ví dụ không bảo đảm atomicity dưới concurrency. Với production, cần unique constraint, transaction/locking hoặc chiến lược idempotency phù hợp và kiểm thử tích hợp. Đừng suy từ unit tests này rằng hệ thống đã race-condition-safe.

## 13. Checklist trước khi merge một subtype handler

1. **Tập subtype:** `sealed Command` có đầy đủ subtype hiện tại không? Khi thêm subtype có nhánh xử lý mới?
2. **Thứ tự nhánh:** Guarded case đứng trước fallback cùng subtype? Có nhánh nào bị dominated?
3. **Null selector:** Đã xác định chính sách `case null` chưa?
4. **Null component:** `var` bind được null; `hasText`/validation có short-circuit an toàn?
5. **Happy path từng subtype:** Handler trả đúng result và state/event như hợp đồng?
6. **Invalid input từng subtype:** Command bị từ chối trước khi gọi operation, không side effect?
7. **Domain conflict:** Duplicate/not-found/closed có nhãn rõ và không thay state?
8. **Repeated command:** Lệnh lặp có hành vi idempotent hay conflict theo chính sách? Có test lặp?
9. **Event ordering:** Event có đúng nội dung, đúng số lần và đúng thứ tự?
10. **Test isolation:** Mỗi test JUnit dựng handler/fixture riêng, không phụ thuộc lượt chạy?
11. **Compiler exhaustiveness:** Mọi subtype được bao phủ, không thêm default tùy tiện?
12. **Boundary integration:** Repository/event publisher production đã được kiểm thử với giao dịch và concurrency phù hợp chưa?
13. **Source level:** Test/build chạy trên Java 21 với đúng `--release 21` và runtime tương ứng?
14. **Trạng thái QA:** Chỉ đánh dấu đạt khi có cả compilation và behavioral assertions, không dựa vào style hoặc code coverage đơn thuần.

## 14. Bài tập tự kiểm tra

**Bài 1.** `new AssignTicket(null,"Ana")` có làm `case AssignTicket(var id,var owner)` không khớp không?

**Đáp án:** Không. Record tồn tại nên component `id` có thể bind null bằng `var`. Guard `hasText(id)` false khiến nhánh guarded bị bỏ qua; fallback `AssignTicket ignored` trả `REJECTED:ASSIGN_FIELDS`.

**Bài 2.** Ticket T1 đã đóng. Lệnh `AssignTicket("T1","Ana")` đi vào nhánh nào?

**Đáp án:** Guard dữ liệu đúng, nên đi vào `assign(id,owner)`. Phương thức kiểm tra ticket closed và trả `CONFLICT:CLOSED:T1`, không phát event. Không phải lỗi pattern mismatch.

**Bài 3.** Vì sao test duplicate phải kiểm tra cả title của Ticket cũ?

**Đáp án:** Handler có thể vô tình ghi đè title khi tạo trùng ID nhưng vẫn trả conflict. Snapshot phải chứng minh dữ liệu cũ được bảo toàn.

**Bài 4.** Thêm `ReopenTicket` vào sealed hierarchy nhưng không thêm case. Vì sao build có thể từ chối?

**Đáp án:** `switch expression` không có default và phải exhaustive. Compiler nhận ra một subtype được phép chưa có nhánh phù hợp.

**Bài 5.** Nếu thêm `default -> "IGNORED"`, vì sao vẫn chưa đủ kiểm thử subtype mới?

**Đáp án:** Compiler có thể chấp nhận fallback, nhưng code chưa xác định ý nghĩa của command mới. Phải thêm domain operation và tests phù hợp, không che thiếu case.

**Bài 6.** Một handler trả `OPENED:T1` nhưng không ghi `OPEN:T1` vào event list. Test chỉ so result có phát hiện không?

**Đáp án:** Không. Cần kiểm tra event count và event content, đặc biệt ở những hành vi side effect.

**Bài 7.** Vì sao test main có thể dùng một Handler chung mà nhiều unit tests JUnit không nên dùng shared mutable Handler?

**Đáp án:** Main cố ý mô phỏng **một workflow có thứ tự**, còn unit tests phải cô lập để không phụ thuộc thứ tự chạy và có thể chạy song song.

**Bài 8.** Nếu cần xác nhận không gửi email khi command bị reject nhưng fake Map không ghi nhận email, nên làm gì?

**Đáp án:** Tách email gateway thành một dependency/port, dùng mock hoặc fake email gateway để assert **không có lời gọi**. Snapshot Map không chứng minh không có side effect ngoài Map.

**Bài 9.** `case null` có liên quan đến exhaustive check subtype như thế nào?

**Đáp án:** Nó định nghĩa cách xử lý selector null. Các case subtype xử lý giá trị command khác null; hai vấn đề cần xem riêng.

**Bài 10.** Vì sao cần test `close T1 twice` dù đã test `close T1` thành công?

**Đáp án:** Vì repeated command có thể tạo event trùng hoặc sửa state lần nữa. Chính sách demo quy định lần hai conflict và không mutation.

## Kết luận

Để **kiểm thử handler theo subtype**, không chỉ gọi mỗi nhánh một lần. Hãy coi mỗi subtype là một **hợp đồng** gồm input hợp lệ, validation failure, trạng thái repository, output và side effects. `sealed Command` + pattern matching `switch` giúp dispatch rõ ràng, giảm cast thủ công và cung cấp kiểm tra exhaustive khi thêm biến thể mới. Guard `when` xử lý điều kiện dữ liệu, còn domain operation quyết định thành công hay conflict.

Bộ kiểm thử tốt nhất có **expected output độc lập**, snapshot state trước/sau, event log có thứ tự, test lệnh lặp và test việc **không gây tác dụng phụ trên đường thất bại**. Compiler bảo đảm cấu trúc nhánh, còn behavioral tests bảo vệ đúng nghiệp vụ. Khi ứng dụng phát triển tới database/messaging/concurrency, bổ sung integration tests cho các ranh giới đó thay vì trông chờ fake in-memory chứng minh mọi thứ.

## Tài liệu tham khảo chính thức

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 21 Language Specification — Switch statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
