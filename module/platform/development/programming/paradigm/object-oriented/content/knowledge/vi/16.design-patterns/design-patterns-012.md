# Command Pattern — Đóng gói yêu cầu thành đối tượng trong Java

**Chương:** OOP → Mẫu thiết kế.  
**Mục tiêu:** hiểu Command Pattern, tách nơi phát sinh yêu cầu khỏi nơi xử lý, tổ chức undo/redo, viết ví dụ Java có thể chạy và nhận diện giới hạn của lệnh bất đồng bộ hoặc có tác dụng phụ.

## 1. Bài toán: một thao tác có thể đến từ nhiều nơi

Giả sử ứng dụng quản lý công việc cho phép:

- Nhấn nút **Thêm công việc** hoặc dùng phím tắt.
- Đánh dấu một công việc **đã hoàn thành**.
- Hoàn tác thao tác gần nhất (**Undo**) và thực hiện lại (**Redo**).
- Về sau, cùng thao tác có thể được gọi từ giao diện web, menu desktop, tác vụ tự động hoặc lịch xử lý.

Nếu nút giao diện trực tiếp chứa mọi logic sửa dữ liệu, mỗi cách gọi mới dễ lặp lại cùng một nghiệp vụ. Để triển khai undo, nút bấm lại phải hiểu chi tiết trạng thái trước khi thao tác.

**Command Pattern** giải quyết bằng cách **biến một yêu cầu thành đối tượng có hợp đồng thực thi**. Nơi phát yêu cầu chỉ cần gửi Command tới một bộ thực thi; Command biết cách gọi đối tượng thực hiện nghiệp vụ và có thể giữ dữ liệu cần cho hành vi bổ sung như lịch sử, ghi log, lập lịch hoặc hoàn tác.

Ví dụ về lời gọi:

~~~java
manager.execute(new AddTaskCommand(board, "T1", "Học Command"));
manager.execute(new CompleteTaskCommand(board, "T1"));

manager.undo(); // Hoàn tác việc đánh dấu hoàn thành
manager.redo(); // Thực hiện lại thao tác đó
~~~

Trong đoạn này, **manager** không biết “thêm việc” hay “hoàn thành việc” cần thay đổi những field nào. Nó quản lý các Command theo một giao thức chung.

## 2. Những vai trò của Command Pattern

| Vai trò | Nhiệm vụ | Trong ví dụ |
| --- | --- | --- |
| **Command** | Hợp đồng cho một hành động được đóng gói | **Command** với **execute()**, **undo()** |
| **Concrete Command** | Lưu các tham số cần thiết và gọi Receiver | **AddTaskCommand**, **CompleteTaskCommand** |
| **Receiver** | Nơi thực sự chứa logic hoặc dữ liệu cần thay đổi | **TaskBoard** |
| **Invoker** | Kích hoạt Command, quản lý lịch sử hoặc lịch chạy | **CommandManager** |
| **Client** | Tạo Command, lựa chọn Receiver và yêu cầu thực hiện | **main**, controller, trình xử lý UI |

~~~mermaid
flowchart LR
    Client["Client / UI"] -->|tạo lệnh| Add["AddTaskCommand"]
    Client -->|tạo lệnh| Done["CompleteTaskCommand"]
    Add --> Invoker["CommandManager"]
    Done --> Invoker
    Invoker -->|execute / undo| Contract["Command"]
    Contract -->|ủy quyền| Receiver["TaskBoard"]
    Invoker <--> History["Undo / Redo stacks"]
~~~

Sơ đồ nhấn mạnh quan hệ logic; **AddTaskCommand** và **CompleteTaskCommand** đều là các triển khai của hợp đồng **Command**. Khi lệnh thực thi, nó gọi phương thức thích hợp trên Receiver.

**Điều quan trọng:** không nhất thiết mọi Command đều có **undo()**. Tài liệu GoF thường mô tả hợp đồng thực thi; khả năng hoàn tác là một mở rộng hay gặp. Ví dụ dưới đây cố ý dùng giao thức **execute/undo** vì yêu cầu nghiệp vụ có Undo/Redo.

### Command không chỉ là một lời gọi được đổi tên

Nếu lệnh chỉ chứa **execute()** gọi một hàm duy nhất, **Runnable** hoặc lambda có thể đủ. Lợi ích rõ hơn khi lệnh là một đơn vị có thể nhận diện và quản lý: có tham số, chính sách lỗi, quyền thực hiện, ghi lịch sử, xếp hàng, hủy, retry hoặc audit. Không nên thêm hàng chục lớp Command cho những thao tác quá đơn giản nếu hệ thống không cần những khả năng đó.

## 3. Thiết kế lệnh và quy tắc Undo/Redo

Trước khi viết code, hãy định nghĩa rõ:

1. **AddTaskCommand** thêm công việc có mã và tiêu đề. Khi undo, xóa chính công việc đã thêm. Khi redo, tạo lại công việc.
2. **CompleteTaskCommand** đặt **done = true**. Khi undo, khôi phục giá trị **done** trước đó (có thể là true hoặc false).
3. **CommandManager.execute(command)** chỉ đưa lệnh vào lịch sử sau khi **execute()** trở về thành công; một lệnh mới xóa lịch sử redo.
4. **undo()** lấy lệnh cuối trong lịch sử, gọi **undo()**, rồi mới chuyển nó sang redo stack.
5. **redo()** lấy lệnh từ redo stack, gọi lại **execute()**, rồi mới đưa nó vào undo stack.
6. Nếu lệnh ném exception, manager **không chuyển lệnh giữa hai stack**. Tuy vậy, điều đó *không tự bảo đảm* Receiver không bị thay đổi một phần trước khi exception xuất hiện.

Trong bài, Receiver là **TaskBoard** lưu trong bộ nhớ và chỉ được thay đổi qua một manager theo từng bước; đây là giả định quan trọng để lịch sử khớp với trạng thái. Nếu code bên ngoài sửa board giữa các lệnh, undo có thể không còn ý nghĩa hoặc bị thất bại.

~~~mermaid
sequenceDiagram
    participant UI as Client
    participant M as CommandManager
    participant C as CompleteTaskCommand
    participant B as TaskBoard
    UI->>M: execute(command)
    M->>C: execute()
    C->>B: setDone("T1", true)
    B-->>C: previousDone
    C-->>M: success
    Note over M: push undo; clear redo
    UI->>M: undo()
    M->>C: undo()
    C->>B: setDone("T1", previousDone)
    C-->>M: success
    Note over M: move from undo to redo
~~~

## 4. Java 17 hoàn chỉnh: Command, Receiver và Invoker

Tạo file **CommandDemo.java**. Chạy được trên JDK 17 trở lên, không cần Spring hoặc thư viện ngoài. Các lớp được lồng trong một file để tiện học; trong dự án thật có thể tách theo package.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class CommandDemo {

    // Command contract: hai thao tác phục vụ lịch sử.
    public interface Command {
        void execute();
        void undo();
    }

    // Dữ liệu chỉ đọc được đưa cho bên ngoài.
    public record TaskView(String id, String title, boolean done) {}

    // Receiver: sở hữu dữ liệu và các bất biến.
    public static final class TaskBoard {
        private static final class Task {
            final String id;
            final String title;
            boolean done;

            Task(String id, String title) {
                this.id = id;
                this.title = title;
            }
        }

        private final Map<String, Task> tasks = new LinkedHashMap<>();

        private void add(String id, String title) {
            id = required(id, "id");
            title = required(title, "title");

            if (tasks.containsKey(id)) {
                throw new IllegalArgumentException(
                        "Mã công việc đã tồn tại: " + id);
            }
            tasks.put(id, new Task(id, title));
        }

        private void remove(String id) {
            if (tasks.remove(id) == null) {
                throw new IllegalArgumentException(
                        "Không tìm thấy công việc: " + id);
            }
        }

        // Trả về trạng thái cũ để Command có thể hoàn tác chính xác.
        private boolean setDone(String id, boolean value) {
            Task task = tasks.get(id);
            if (task == null) {
                throw new IllegalArgumentException(
                        "Không tìm thấy công việc: " + id);
            }
            boolean previous = task.done;
            task.done = value;
            return previous;
        }

        public List<TaskView> snapshot() {
            List<TaskView> result = new ArrayList<>();
            for (Task task : tasks.values()) {
                result.add(new TaskView(
                        task.id, task.title, task.done));
            }
            return List.copyOf(result);
        }
    }

    public static final class AddTaskCommand implements Command {
        private final TaskBoard board;
        private final String id;
        private final String title;
        private boolean active;

        public AddTaskCommand(TaskBoard board, String id, String title) {
            this.board = Objects.requireNonNull(board, "board");
            this.id = required(id, "id");
            this.title = required(title, "title");
        }

        @Override
        public void execute() {
            if (active) {
                throw new IllegalStateException(
                        "Lệnh thêm đã được thực hiện");
            }
            board.add(id, title);
            active = true;
        }

        @Override
        public void undo() {
            if (!active) {
                throw new IllegalStateException(
                        "Không thể undo lệnh chưa thực hiện");
            }
            board.remove(id);
            active = false;
        }
    }

    public static final class CompleteTaskCommand implements Command {
        private final TaskBoard board;
        private final String id;
        private boolean active;
        private boolean previousDone;

        public CompleteTaskCommand(TaskBoard board, String id) {
            this.board = Objects.requireNonNull(board, "board");
            this.id = required(id, "id");
        }

        @Override
        public void execute() {
            if (active) {
                throw new IllegalStateException(
                        "Lệnh hoàn thành đã được thực hiện");
            }
            previousDone = board.setDone(id, true);
            active = true;
        }

        @Override
        public void undo() {
            if (!active) {
                throw new IllegalStateException(
                        "Không thể undo lệnh chưa thực hiện");
            }
            board.setDone(id, previousDone);
            active = false;
        }
    }

    // Invoker: có thể thực thi nhiều loại Command.
    public static final class CommandManager {
        private final Deque<Command> undoStack = new ArrayDeque<>();
        private final Deque<Command> redoStack = new ArrayDeque<>();

        public void execute(Command command) {
            Objects.requireNonNull(command, "command");

            // Chỉ cập nhật lịch sử sau khi lệnh thành công.
            command.execute();
            undoStack.push(command);
            redoStack.clear();
        }

        public boolean undo() {
            if (undoStack.isEmpty()) {
                return false;
            }
            Command command = undoStack.peek();
            command.undo(); // Nếu lỗi, giữ nguyên lịch sử.
            undoStack.pop();
            redoStack.push(command);
            return true;
        }

        public boolean redo() {
            if (redoStack.isEmpty()) {
                return false;
            }
            Command command = redoStack.peek();
            command.execute(); // Nếu lỗi, giữ nguyên lịch sử.
            redoStack.pop();
            undoStack.push(command);
            return true;
        }

        public boolean canUndo() {
            return !undoStack.isEmpty();
        }

        public boolean canRedo() {
            return !redoStack.isEmpty();
        }
    }

    private static String required(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " không được rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        TaskBoard board = new TaskBoard();
        CommandManager manager = new CommandManager();

        manager.execute(new AddTaskCommand(
                board, "T1", "Học Command Pattern"));
        manager.execute(new CompleteTaskCommand(board, "T1"));

        System.out.println(board.snapshot());

        manager.undo();
        System.out.println(board.snapshot());

        manager.redo();
        System.out.println(board.snapshot());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CommandDemo.java
java CommandDemo
~~~

Kết quả:

~~~text
[TaskView[id=T1, title=Học Command Pattern, done=true]]
[TaskView[id=T1, title=Học Command Pattern, done=false]]
[TaskView[id=T1, title=Học Command Pattern, done=true]]
~~~

### Phân tích chi tiết từng vai trò

**TaskBoard (Receiver)** chịu trách nhiệm giữ dữ liệu và các bất biến cơ bản như không trùng mã, không tồn tại tiêu đề rỗng và không thao tác công việc không tồn tại. Command không cần biết cách lưu danh sách bên trong Receiver.

**AddTaskCommand** chứa đối tượng board, mã công việc, tiêu đề và cờ **active**. Sau khi thêm thành công, **active = true**. Undo xóa công việc đó rồi đặt lại cờ. Vì vậy, cùng instance có thể được redo sau khi undo. Đây là lựa chọn cụ thể của bài: không phải mọi Command ngoài đời đều có thể hoặc nên thực thi lặp lại.

**CompleteTaskCommand** ghi nhớ **previousDone** của chính lần thực thi gần nhất. Undo khôi phục giá trị cũ, thay vì luôn ép **false**. Đây là điểm quan trọng: hoàn tác phải khôi phục *trạng thái trước thao tác*, không đoán trạng thái.

**CommandManager** điều phối lịch sử nhưng không hiểu nghiệp vụ từng Command. Nó lưu **đối tượng lệnh**, không chỉ tên thao tác. Vì thế lệnh có thể giữ dữ liệu để undo. Lệnh mới thành công làm mất nhánh redo trước đó, giống hành vi phổ biến của trình soạn thảo.

**TaskView** là **record** bất biến, dùng làm snapshot cho code bên ngoài. **List.copyOf(...)** tạo danh sách không cho sửa thông qua kết quả trả về. Vì các thành phần của record là **String/boolean**, bản thân phần tử trong ví dụ cũng không mang trạng thái mutable.

### Giới hạn của ví dụ

- **TaskBoard** và manager chạy trong một tiến trình, một luồng thực hiện tuần tự. Chúng không triển khai khóa, transaction, persistence hoặc phân quyền.
- Phương thức mutation của **TaskBoard** được đặt **private**; các lớp lồng trong cùng top-level class có quyền truy cập private của nhau theo quy tắc Java. Trong codebase thật, hãy tổ chức API để chỉ application service/command handler có thẩm quyền sửa Receiver.
- Manager **không kiểm soát việc một instance Command được truyền qua hai manager khác nhau**. Cờ **active** sẽ từ chối một số lần gọi sai, nhưng đây không phải một cơ chế sở hữu/lifecycle tổng quát.
- Khi người dùng muốn “hoàn tác việc gửi email” hoặc “hoàn tác thanh toán”, thao tác thực tế có thể đã ra khỏi hệ thống. Khi đó **undo()** kiểu đảo trạng thái RAM không đủ; cần quy trình bù trừ, nếu có.
- Việc giữ **lịch sử trong bộ nhớ** làm mất lịch sử khi khởi động lại; cần giải pháp lưu trữ riêng nếu tính năng yêu cầu phục hồi sau restart.

## 5. Undo và Redo thực sự cần điều kiện gì?

Khả năng undo an toàn phụ thuộc vào bản chất hành động.

| Lệnh | Cách hoàn tác có thể có | Những điều cần lưu ý |
| --- | --- | --- |
| Đổi trạng thái checkbox | Khôi phục giá trị trước đó | Receiver không bị thay đổi trái phép ở giữa |
| Thêm dòng trong tài liệu | Xóa đúng đoạn đã chèn | Phải ghi lại vị trí, ID hoặc version để không xóa nhầm |
| Xóa công việc | Lưu bản chụp cần thiết rồi tạo lại | Khôi phục đủ thuộc tính và thứ tự nếu cần |
| Di chuyển file nội bộ | Di chuyển về vị trí cũ | Cần xử lý trùng tên, mất file, quyền truy cập |
| Gửi email | Thường không thể thu hồi email đã gửi | Có thể cần tạo một *lệnh mới* gửi email đính chính |
| Thanh toán thành công | Không đơn thuần đảo dấu số dư | Hoàn tiền là nghiệp vụ riêng, có ràng buộc và trạng thái độc lập |

Một lệnh **undoable** nên thỏa các kỳ vọng:

1. Có đủ thông tin trước thao tác để xác định hành vi bù trừ.
2. Khi undo thành công, những bất biến nghiệp vụ cần thiết được bảo toàn.
3. Khi undo thất bại, caller nhận lỗi rõ ràng; không giả vờ thành công.
4. Nếu có sửa đổi xen kẽ, cần quyết định rõ cách phát hiện xung đột hoặc tái tính toán.
5. Nếu có side effect ngoài hệ thống, phải có chính sách xử lý riêng.

Đôi khi **memento/snapshot** hữu ích: lưu trạng thái trước khi thực thi để phục hồi. Với dữ liệu lớn, lưu toàn bộ snapshot cho mỗi command có thể tốn bộ nhớ; lưu phần chênh lệch (*delta*) hoặc một cách biểu diễn thao tác đảo ngược thường hiệu quả hơn, nhưng phức tạp hơn. Chọn giải pháp dựa trên nhu cầu và kích thước dữ liệu.

### Vì sao manager thay đổi stack sau khi lệnh thành công?

Giả sử **undo()** ném exception vì dữ liệu đã bị một tác vụ khác thay đổi. Nếu manager đã pop lệnh khỏi **undoStack** trước khi gọi undo thì lịch sử sẽ mất lệnh dù chưa hoàn tác được. Vì vậy, trong ví dụ:

~~~java
Command command = undoStack.peek();
command.undo();          // Chưa động tới stack
undoStack.pop();         // Chỉ sau khi thành công
redoStack.push(command);
~~~

**Lưu ý:** nếu **command.undo()** đã sửa dữ liệu một phần rồi ném lỗi, việc để nguyên stack vẫn chưa giải quyết được trạng thái Receiver. Với nhiều thay đổi cần thực hiện như một khối, hãy dùng transaction, command có phương thức xử lý lỗi phù hợp hoặc cơ chế rollback có kiểm chứng.

## 6. Kiểm thử Command và lịch sử

Các kiểm thử sau dùng **JUnit 5 Jupiter**. Đặt trong **CommandDemoTest.java** cùng package với ví dụ.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class CommandDemoTest {

    @Test
    void executeUndoRedoGiuDungTrangThai() {
        var board = new CommandDemo.TaskBoard();
        var manager = new CommandDemo.CommandManager();

        manager.execute(new CommandDemo.AddTaskCommand(
                board, "T1", "Học Java"));
        manager.execute(new CommandDemo.CompleteTaskCommand(
                board, "T1"));

        assertEquals(List.of(
                new CommandDemo.TaskView("T1", "Học Java", true)),
                board.snapshot());

        assertTrue(manager.undo());
        assertEquals(List.of(
                new CommandDemo.TaskView("T1", "Học Java", false)),
                board.snapshot());

        assertTrue(manager.redo());
        assertEquals(List.of(
                new CommandDemo.TaskView("T1", "Học Java", true)),
                board.snapshot());
    }

    @Test
    void lenhMoiXoaNhanhRedoCu() {
        var board = new CommandDemo.TaskBoard();
        var manager = new CommandDemo.CommandManager();

        manager.execute(new CommandDemo.AddTaskCommand(
                board, "T1", "Làm A"));
        manager.execute(new CommandDemo.CompleteTaskCommand(
                board, "T1"));

        assertTrue(manager.undo());
        assertTrue(manager.canRedo());

        manager.execute(new CommandDemo.AddTaskCommand(
                board, "T2", "Làm B"));

        assertFalse(manager.canRedo());
        assertFalse(manager.redo());
        assertEquals(2, board.snapshot().size());
    }

    @Test
    void lenhThatBaiKhongThemVaoLichSu() {
        var board = new CommandDemo.TaskBoard();
        var manager = new CommandDemo.CommandManager();

        assertThrows(IllegalArgumentException.class, () ->
                manager.execute(new CommandDemo.CompleteTaskCommand(
                        board, "KHONG-TON-TAI")));

        assertFalse(manager.canUndo());
        assertFalse(manager.canRedo());
    }

    @Test
    void undoLenhThemXoaDungCongViec() {
        var board = new CommandDemo.TaskBoard();
        var manager = new CommandDemo.CommandManager();

        manager.execute(new CommandDemo.AddTaskCommand(
                board, "T1", "Viết test"));
        assertTrue(manager.undo());
        assertTrue(board.snapshot().isEmpty());

        assertTrue(manager.redo());
        assertEquals("T1", board.snapshot().get(0).id());
    }
}
~~~

Test kiểm tra kết quả nghiệp vụ và lịch sử, không giả định manager gọi chính xác bao nhiêu hàm nội bộ. Nếu dự án có nhiều Command, có thể kiểm tra hợp đồng chung bằng test tham số hóa; thêm test riêng cho các quy tắc đặc thù, nhất là khi Command thay đổi nhiều đối tượng.

## 7. Command mở đường cho macro, queue và lịch thực hiện

### 7.1. Macro Command: một lệnh gồm nhiều lệnh

Có thể viết lệnh kết hợp:

~~~java
final class CompositeCommand implements CommandDemo.Command {
    private final java.util.List<CommandDemo.Command> commands;

    CompositeCommand(java.util.List<CommandDemo.Command> commands) {
        this.commands = java.util.List.copyOf(commands);
    }

    @Override
    public void execute() {
        for (var command : commands) {
            command.execute();
        }
    }

    @Override
    public void undo() {
        for (int i = commands.size() - 1; i >= 0; i--) {
            commands.get(i).undo();
        }
    }
}
~~~

**Quan trọng:** đây chỉ là phiên bản minh họa ý tưởng **Composite Command**, **chưa bảo đảm atomicity**. Nếu lệnh thứ ba lỗi trong **execute()**, hai lệnh đầu có thể đã chạy; undo toàn bộ danh sách lúc đó cũng có thể sai. Để dùng thật, cần theo dõi các lệnh đã hoàn tất, undo phần đã thực hiện theo thứ tự ngược nếu phù hợp, hoặc đặt tất cả cập nhật vào transaction. Thậm chí rollback bù trừ có thể thất bại; phải định nghĩa trạng thái lỗi và cách khôi phục.

### 7.2. Queue Command: tách thời điểm nhận và xử lý yêu cầu

Vì Command đại diện một yêu cầu, Invoker có thể xếp hàng:

~~~java
java.util.Queue<CommandDemo.Command> queue =
        new java.util.ArrayDeque<>();

queue.add(new CommandDemo.AddTaskCommand(
        new CommandDemo.TaskBoard(), "T1", "Xử lý sau"));

CommandDemo.Command next = queue.remove();
next.execute();
~~~

Ví dụ trên chỉ là **queue trong RAM**, chưa phải hệ thống message queue bền vững. Đừng đưa nguyên một Java object chứa Receiver, kết nối database hoặc closure rồi giả định có thể serialize và chạy ở máy khác.

Trong hệ thống phân tán, thường dùng **mô tả lệnh** chứa dữ liệu như **commandId**, **type**, **taskId**, **payload**, **createdAt**, **expectedVersion**. Một handler ở phía tiêu thụ dựng lại nghiệp vụ từ mô tả đó và phụ thuộc cần thiết.

~~~java
// Mô tả dữ liệu lệnh, không chứa tham chiếu TaskBoard.
record CompleteTaskRequest(
        String commandId,
        String taskId,
        long expectedVersion
) {}
~~~

Command object bên trong tiến trình và thông điệp yêu cầu qua queue **có thể khác kiểu**, dù cùng diễn đạt một hành động. Khi chuyển từ local queue sang broker, cần thiết kế riêng việc serialize, version schema, security, timeout, dead-letter, retry và observability.

### 7.3. Retry và idempotency

Một lệnh có thể được gửi lại khi mạng timeout dù phía xử lý thực tế đã hoàn tất. Nếu **AddTaskCommand** được thực hiện lại ở Receiver, thao tác có thể báo trùng ID. Với hệ thống thật, cần thiết kế:

- **Command ID / idempotency key** xác định duy nhất một yêu cầu nghiệp vụ.
- Quy tắc xử lý lặp: trả lại kết quả cũ, từ chối trùng hoặc bảo đảm không tạo side effect lần nữa theo contract.
- Transaction/unique constraint hoặc cơ chế lưu trạng thái xử lý để nhiều worker không thực hiện trùng.
- Chính sách retry dựa trên tính chất lỗi: lỗi tạm thời khác lỗi kiểm tra nghiệp vụ.

**Đừng nhầm redo với retry**. **Redo** là hành động người dùng chọn để thực hiện lại sau khi undo; **retry** là nỗ lực xử lý lại một yêu cầu chưa xác định kết quả hoặc thất bại. Một Command có thể không an toàn nếu được tự động thực hiện hai lần.

## 8. So sánh Command với các khái niệm gần nó

| Khái niệm | Mục đích chính | Điểm phân biệt |
| --- | --- | --- |
| **Command Pattern** | Biến yêu cầu thành đối tượng để truyền, ghi nhận, lập lịch, quản lý vòng đời | Hướng đến **hành động được yêu cầu** |
| **Strategy Pattern** | Đóng gói các thuật toán thay thế nhau | Hướng đến **cách thực hiện cùng một tác vụ** |
| **Observer Pattern** | Phát thông báo cho nhiều bên đăng ký khi có sự kiện | Hướng đến **phản ứng khi sự kiện xảy ra** |
| **State Pattern** | Hành vi thay đổi theo trạng thái hiện tại của cùng Context | Hướng đến **vòng đời/trạng thái của đối tượng** |
| **Memento Pattern** | Lưu và phục hồi ảnh chụp trạng thái mà không lộ chi tiết nội bộ | Có thể kết hợp với Command để undo |
| **Event** | Ghi nhận **điều đã xảy ra** | Khác Command, vốn diễn đạt **mong muốn hành động** |
| **Runnable/Callable** | Abstraction hàm thực thi trong Java | Có thể đủ cho hành động đơn giản; không tự cung cấp danh tính nghiệp vụ, undo hoặc persistence |

Ví dụ:

- **Command:** “Hãy hoàn thành công việc T1”.
- **Event:** “Công việc T1 đã hoàn thành”.
- **Strategy:** “Dùng thuật toán tính điểm ưu tiên A hay B cho công việc?”.
- **State:** “Công việc đang NEW hay DONE nên những thao tác nào được cho phép?”.

Một handler có thể xử lý Command, thay đổi State rồi phát Event. Chúng phối hợp được với nhau nhưng không thay thế nhau.

## 9. Dùng Command trong ứng dụng thực tế

### 9.1. UI desktop và menu

Một hành động như Save, Undo, Redo, Delete Selection có thể xuất hiện ở nút toolbar, menu ngữ cảnh và phím tắt. Những Invoker khác nhau tạo/kích hoạt cùng kiểu Command mà không sao chép logic nghiệp vụ.

Với **JavaFX** hoặc **Swing**, việc này đặc biệt tự nhiên: UI handler làm nhiệm vụ chuyển ý định người dùng thành command, còn Receiver/service chịu trách nhiệm thực thi. Trong ứng dụng rất nhỏ, action callback trực tiếp vẫn có thể phù hợp hơn mô hình nhiều lớp.

### 9.2. Service backend và CQRS

Trong backend Java/Spring, application service có thể đóng vai trò command handler:

~~~java
// Phác thảo kiến trúc, không phải class Spring chạy độc lập:
record ApproveInvoiceCommand(String invoiceId, String actorId) {}

final class ApproveInvoiceHandler {
    private final InvoiceRepository invoices;

    ApproveInvoiceHandler(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    void handle(ApproveInvoiceCommand command) {
        // Kiểm tra quyền, load aggregate, kiểm tra trạng thái,
        // thực hiện chuyển đổi, lưu trong transaction phù hợp.
    }
}
~~~

Đoạn này là **phác thảo** vì **InvoiceRepository** và nghiệp vụ hóa đơn chưa được định nghĩa. Nó cho thấy một biến thể thường gặp: **Command là DTO bất biến**, **Handler** thực hiện nghiệp vụ, khác ví dụ Command object tự mang theo Receiver và **execute()**. Hai cách đều dùng ý tưởng đóng gói yêu cầu nhưng có lựa chọn đánh đổi khác nhau.

**CQRS** (Command Query Responsibility Segregation) phân tách đường xử lý thay đổi trạng thái khỏi đường truy vấn dữ liệu; nó không bắt buộc mọi dự án dùng command bus, event sourcing hoặc hai database. Một Command handler rõ ràng cũng có thể có ích trong kiến trúc thông thường.

### 9.3. Giao dịch, concurrency và phân quyền

Trong môi trường nhiều request:

- Kiểm tra **authorization** theo actor, resource và operation ở phía server. Không cho phép client gửi tên class hay payload tùy ý để gọi bất cứ phương thức nào.
- Sử dụng **version/optimistic locking** hoặc update có điều kiện để tránh hai lệnh ghi đè thay đổi của nhau.
- Xác định ranh giới **transaction** của mỗi Command; một lịch sử stack RAM không thay thế giao dịch.
- Nếu cần audit, ghi danh tính lệnh, tác nhân, thời điểm, tài nguyên, kết quả và thông tin lỗi theo chính sách bảo mật; tránh lưu dữ liệu nhạy cảm không cần thiết.
- Nếu Command tạo side effect ngoài database, cân nhắc **outbox**, idempotency, saga/compensation và chính sách vận hành khi lỗi giữa chừng.

**Một lịch sử undo trên UI không nên được coi là cơ chế hủy giao dịch thanh toán thật.** Sau khi thay đổi có hiệu lực bên ngoài, “hoàn tác” phải là nghiệp vụ bù trừ được định nghĩa rõ, có kiểm toán và giới hạn quyền truy cập.

## 10. Khi nào nên và không nên dùng Command?

**Nên cân nhắc Command nếu:**

- Cùng một hành động được gọi từ nhiều nơi và cần một hợp đồng thực thi thống nhất.
- Có yêu cầu **undo/redo**, macro, lịch sử hoặc replay có kiểm soát.
- Cần đưa yêu cầu vào queue, lên lịch, ghi audit hoặc áp retry/idempotency.
- Muốn tách handler nghiệp vụ khỏi UI, controller, scheduler hoặc cơ chế truyền thông.
- Muốn chuyển các thao tác sang đối tượng có định danh và dữ liệu rõ để kiểm thử độc lập.

**Không nên dùng chỉ vì mọi thao tác đều là hàm**. Một phép tính thuần túy **calculateTotal()**, một helper nội bộ nhỏ hoặc một button callback không có vòng đời/hành vi quản lý đặc biệt có thể không cần cả một class Command, Manager và factory.

Nếu chỉ cần trì hoãn một callback trong cùng tiến trình, có thể dùng **Runnable**:

~~~java
Runnable task = () -> System.out.println("Đã thực thi");
task.run();
~~~

Command Pattern phát huy giá trị khi ngoài “gọi sau” còn có **ý nghĩa nghiệp vụ, tham số, lifecycle, lịch sử, khả năng kiểm soát lỗi hoặc chính sách thực thi** cần được biểu diễn rõ.

### Các lỗi thường gặp

| Lỗi | Tác động | Cách khắc phục |
| --- | --- | --- |
| Command chứa cả giao diện, truy vấn DB, gửi email và quy tắc không liên quan | God object, khó test | Đặt nghiệp vụ ở Receiver/service; Command giữ mục đích và tham số |
| Undo luôn “đặt cờ false” bất kể giá trị trước đó | Phá trạng thái gốc | Lưu giá trị cũ hoặc thao tác nghịch đảo chính xác |
| Pop lịch sử trước khi biết undo thành công | Mất lệnh khi gặp lỗi | Chỉ cập nhật stack sau khi thao tác thành công |
| Tái sử dụng một Command instance đang active | Thực thi lặp ngoài ý định | Định nghĩa vòng đời và trạng thái của từng lệnh |
| Retry lệnh có side effect mà không có idempotency | Gửi trùng, ghi trùng, thu tiền hai lần | Command ID + guard/transaction phù hợp |
| Xem command object trong RAM là message bền vững | Không serialize được Receiver và phụ thuộc | Dùng request DTO/handler và schema có phiên bản |
| Lịch sử undo dùng chung nhiều user không phân biệt ngữ cảnh | Người này tác động lên lịch sử của người khác | Phân vùng theo phiên/người dùng/tài nguyên và kiểm tra quyền |
| Lạm dụng Command cho thao tác không cần quản lý | Boilerplate và thêm tầng khó đọc | Giữ phương thức/lambda trực tiếp khi đủ rõ |

## 11. Bài tập thực hành

Thiết kế một trình chỉnh sửa văn bản đơn giản bằng Java, có **TextDocument** làm Receiver và **CommandManager** làm Invoker.

Các lệnh yêu cầu:

1. **AppendTextCommand(text):** thêm văn bản vào cuối tài liệu; khi undo, chỉ loại bỏ đoạn chính nó đã thêm, đúng vị trí.
2. **ReplaceTextCommand(from, to):** thay đoạn văn bản đầu tiên khớp điều kiện; lưu đủ thông tin để undo chính xác.
3. **ClearDocumentCommand:** xóa toàn bộ; có thể lưu snapshot trước khi xóa để phục hồi.
4. Hỗ trợ undo/redo nhiều bước và xóa lịch sử redo khi thực thi một lệnh mới.

**Tình huống test nên có:** append hai lần rồi undo/redo; replace không tìm thấy đoạn cần thay; clear rồi phục hồi Unicode có dấu; lệnh lỗi không được ghi lịch sử; sửa tài liệu ngoài manager phải được từ chối hoặc gây lỗi xung đột rõ.

Thử mở rộng: lưu thông tin Command dưới dạng DTO có **commandId** và **expectedVersion** để áp lên tài liệu đã lưu database. Phân biệt phần dữ liệu tuần tự hóa được với Receiver/runtime service. Nếu hai người cùng sửa một tài liệu, hãy giải thích cách nhận biết và xử lý xung đột thay vì tin vào stack undo trong RAM.

**Tiêu chí đạt:** client gửi cùng một hợp đồng Command; Receiver giữ logic chỉnh sửa; lịch sử thay đổi chính xác sau khi lệnh hoàn tất; các thao tác undo/redo bảo toàn dữ liệu; có test cho đường hợp lệ, lỗi và xung đột.

**Điểm cần nhớ:** Command Pattern là cách đóng gói **ý định thực hiện một hành động** để có thể chuyển giao, quản lý và xử lý qua một giao diện chung. Nó giúp tách Invoker khỏi Receiver, nhưng undo, retry, lưu lịch sử, phân quyền và tính nhất quán dữ liệu đều cần được thiết kế tường minh theo tính chất nghiệp vụ thực tế.