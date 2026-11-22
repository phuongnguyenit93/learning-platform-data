# Command Pattern — Encapsulating Requests as Objects in Java

**Chapter:** OOP → Design Patterns.  
**Objective:** Understand Command Pattern, separate request producers from handlers, organize undo/redo, write a runnable Java example, and recognize the limitations of asynchronous commands and side-effectful operations.

## 1. The Problem: An Action Can Originate in Many Places

Suppose a task-management application allows users to:

- Click **Add Task** or use a keyboard shortcut.
- Mark a task as **completed**.
- Undo the most recent action (**Undo**) and perform it again (**Redo**).
- Later, invoke the same operation through a web interface, desktop menu, automated job, or scheduled process.

If UI buttons contain all data-modification logic, adding another invocation path tends to duplicate the business operation. Implementing undo then also forces the button code to understand pre-action state.

**Command Pattern** solves this by **turning a request into an object with an execution contract**. A request producer merely passes a Command to an invoker; the Command knows how to invoke the business Receiver and may retain data for history, logging, scheduling, or undo.

Example invocation:

~~~java
manager.execute(new AddTaskCommand(board, "T1", "Học Command"));
manager.execute(new CompleteTaskCommand(board, "T1"));

manager.undo(); // Hoàn tác việc đánh dấu hoàn thành
manager.redo(); // Thực hiện lại thao tác đó
~~~

In this snippet, **manager** does not know which fields must change to “add a task” or “complete a task.” It manages Commands through a common protocol.

## 2. Command Pattern Roles

| Role | Responsibility | In this example |
| --- | --- | --- |
| **Command** | Contract for an encapsulated action | **Command** with **execute()**, **undo()** |
| **Concrete Command** | Stores required parameters and invokes the Receiver | **AddTaskCommand**, **CompleteTaskCommand** |
| **Receiver** | Owns the business logic or data being modified | **TaskBoard** |
| **Invoker** | Triggers Commands and manages history or scheduling | **CommandManager** |
| **Client** | Creates Commands, selects Receivers, and requests execution | **main**, controller, UI handler |

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

The diagram emphasizes logical relationships; both **AddTaskCommand** and **CompleteTaskCommand** implement the **Command** contract. During execution, they invoke appropriate methods on the Receiver.

**Key point:** not every Command requires **undo()**. GoF descriptions usually focus on an execution contract; undo support is a common extension. This example deliberately uses **execute/undo** because its requirements include Undo/Redo.

### Command Is More Than a Renamed Function Call

If a Command only implements **execute()** to invoke a single function, a **Runnable** or lambda may suffice. The benefits become clearer when a request needs identity and management: parameters, error policies, authorization, history, queues, cancellation, retries, or auditing. Avoid creating dozens of Command classes for trivial operations without those needs.

## 3. Designing Commands and Undo/Redo Rules

Before writing code, specify:

1. **AddTaskCommand** adds a task with an ID and title. Undo removes exactly that task; redo recreates it.
2. **CompleteTaskCommand** sets **done = true**. Undo restores the prior value of **done** (which may be true or false).
3. **CommandManager.execute(command)** adds a Command to history only after **execute()** succeeds, and a new command clears redo history.
4. **undo()** peeks at the most recent history command, invokes **undo()**, then moves it to the redo stack.
5. **redo()** peeks at the redo stack, invokes **execute()** again, then moves the command to the undo stack.
6. If a command throws, the manager **does not move the command between stacks**. This alone *does not guarantee* that Receiver was not partially modified before the exception.

This example uses an in-memory **TaskBoard** updated sequentially through one manager. That assumption keeps history aligned with state. If external code modifies the board between commands, undo may become meaningless or fail.

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

## 4. Complete Java 17 Example: Command, Receiver, and Invoker

Create **CommandDemo.java**. It runs on JDK 17+ without Spring or external libraries. Classes are nested in one file for learning; production projects may split them into appropriate packages.

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

Compile and run:

~~~bash
javac CommandDemo.java
java CommandDemo
~~~

Output:

~~~text
[TaskView[id=T1, title=Học Command Pattern, done=true]]
[TaskView[id=T1, title=Học Command Pattern, done=false]]
[TaskView[id=T1, title=Học Command Pattern, done=true]]
~~~

### Detailed Analysis of Each Role

**TaskBoard (Receiver)** owns the data and basic invariants: IDs must be unique, titles nonblank, and nonexistent tasks cannot be modified. Commands need not know how the Receiver stores its internal list.

**AddTaskCommand** holds a board reference, task ID, title, and **active** flag. After a successful add, **active = true**. Undo removes the task and resets the flag, allowing the same instance to redo after undo. That is specific to this example: not every real Command can or should be executed repeatedly.

**CompleteTaskCommand** remembers **previousDone** from its latest execution. Undo restores that previous value rather than always forcing **false**. An important rule: undo should restore *the pre-operation state*, not guess it.

**CommandManager** coordinates history without understanding the business meaning of individual Commands. It stores **command objects**, not merely action names, allowing commands to retain data needed for undo. Executing a new command successfully discards the old redo branch, as is common in text editors.

**TaskView** is an immutable **record** used as a snapshot for external code. **List.copyOf(...)** returns an unmodifiable list. Because the record components are **String/boolean**, elements in this example carry no mutable state either.

### Limitations of the Example

- **TaskBoard** and the manager run sequentially in one thread and process. They implement no locks, transactions, persistence, or authorization.
- **TaskBoard** mutation methods are **private**; nested classes of the same top-level class may access one another private members under Java rules. In production, design APIs so only authorized application services/command handlers can modify the Receiver.
- The manager **does not prevent a Command instance from being passed to two different managers**. The **active** flag rejects some invalid calls but is not a general ownership/lifecycle mechanism.
- When users request “undo sending an email” or “undo payment,” the real-world action may already have left the system. Then RAM-state reversal through **undo()** is insufficient; use a compensating business workflow where available.
- Keeping **history in memory** loses it after restart; persistence is needed if recovery across restarts is required.

## 5. What Does Safe Undo/Redo Require?

Safe undo depends on the nature of the action.

| Command | Possible inverse | Considerations |
| --- | --- | --- |
| Change checkbox state | Restore previous value | Receiver must not have been modified unexpectedly in between |
| Insert a document line | Remove the exact inserted segment | Record location, ID, or version to avoid deleting the wrong segment |
| Delete a task | Save a necessary snapshot, then recreate | Restore all required attributes and order |
| Move an internal file | Move back to its previous location | Handle naming conflicts, missing files, and access permissions |
| Send email | Usually cannot retract a delivered message | May need *a new command* to send a correction |
| Complete payment | Cannot simply negate an account balance | Refund is a separate business workflow with its own constraints and states |

An **undoable** command should meet these expectations:

1. It retains enough information about the prior state to determine a valid inverse action.
2. A successful undo preserves required business invariants.
3. A failed undo reports a clear error to callers rather than pretending to succeed.
4. Concurrent/intervening edits have explicit conflict detection or recalculation rules.
5. Side effects outside the local system are handled under a separate policy.

A **memento/snapshot** can sometimes help: store the pre-execution state for restoration. For large data sets, full snapshots per command may consume too much memory; recording deltas or inverse-operation descriptions may be more efficient but more complex. Choose based on data size and needs.

### Why Does the Manager Change Stacks Only After Success?

Suppose **undo()** throws because another task changed the data. If the manager pops the Command from **undoStack** before invoking undo, history loses that command even though no undo completed. The example therefore does the following:

~~~java
Command command = undoStack.peek();
command.undo();          // Chưa động tới stack
undoStack.pop();         // Chỉ sau khi thành công
redoStack.push(command);
~~~

**Caution:** if **command.undo()** partially modifies data and then throws, leaving the stack unchanged still does not repair Receiver state. For multistep atomic changes, use transactions, suitable command error handling, or a verified rollback mechanism.

## 6. Testing Commands and History

The following tests use **JUnit 5 Jupiter**. Place them in **CommandDemoTest.java** in the same package as the example.

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

Tests verify business results and history without assuming the manager invokes an exact number of internal methods. If many Command types exist, consider parameterized tests for shared contracts and specific tests for complex rules, particularly when Commands affect several objects.

## 7. Command Enables Macros, Queues, and Scheduling

### 7.1. Macro Command: One Command Containing Several Others

Commands can be composed:

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

**Important:** this snippet only illustrates a **Composite Command**; it **does not guarantee atomicity**. If the third command fails during **execute()**, the first two may already have completed, and undoing the whole list may then be incorrect. A production implementation must track completed commands and undo only those in reverse order when appropriate, or execute all updates in a transaction. Even compensating rollback can fail, so define failure states and recovery procedures.

### 7.2. Queueing Commands: Separate Receipt from Execution

Because Command represents a request, an Invoker can enqueue it:

~~~java
java.util.Queue<CommandDemo.Command> queue =
        new java.util.ArrayDeque<>();

queue.add(new CommandDemo.AddTaskCommand(
        new CommandDemo.TaskBoard(), "T1", "Xử lý sau"));

CommandDemo.Command next = queue.remove();
next.execute();
~~~

The snippet shows an **in-memory queue**, not a durable message queue. Do not enqueue a Java object holding a Receiver, database connection, or closure and assume it can be serialized and executed on another machine.

Distributed systems commonly use **command descriptions** carrying fields such as **commandId**, **type**, **taskId**, **payload**, **createdAt**, and **expectedVersion**. A consumer-side handler reconstructs the business operation from that description and appropriate dependencies.

~~~java
// Mô tả dữ liệu lệnh, không chứa tham chiếu TaskBoard.
record CompleteTaskRequest(
        String commandId,
        String taskId,
        long expectedVersion
) {}
~~~

A local Command object and a request message sent through a queue **may have different types** despite representing the same action. Moving from a local queue to a broker requires explicit serialization, schema versioning, security, timeouts, dead letters, retries, and observability.

### 7.3. Retries and Idempotency

A command may be redelivered after a network timeout even though the handler already completed it. Re-executing **AddTaskCommand** against the Receiver may report a duplicate ID. Production systems should define:

- A **Command ID / idempotency key** uniquely identifying a business request.
- Duplicate-processing rules: return an earlier result, reject duplicates, or prevent repeated side effects according to the contract.
- Transactions/unique constraints or recorded processing state so concurrent workers cannot execute the same command twice.
- Retry policies based on error types: transient failures differ from business-validation errors.

**Do not confuse redo with retry**. **Redo** is a user-requested repeat after undo; **retry** is another attempt to process a request with an unknown result or previous failure. Automatic execution twice may be unsafe for some Commands.

## 8. Comparing Command with Related Concepts

| Concept | Main purpose | Distinguishing feature |
| --- | --- | --- |
| **Command Pattern** | Turns requests into objects for passing, recording, scheduling, and lifecycle management | Focuses on **the action requested** |
| **Strategy Pattern** | Encapsulates interchangeable algorithms | Focuses on **how to perform one task** |
| **Observer Pattern** | Notifies several subscribers after an event | Focuses on **reactions to events** |
| **State Pattern** | Changes behavior according to the state of the same Context | Focuses on **object lifecycle/state** |
| **Memento Pattern** | Saves/restores snapshots without exposing internals | Can be combined with Command for undo |
| **Event** | Records **what has happened** | Unlike Command, which expresses **an intended action** |
| **Runnable/Callable** | Java execution-function abstractions | May suffice for simple actions; do not inherently provide business identity, undo, or persistence |

Examples:

- **Command:** “Complete task T1.”
- **Event:** “Task T1 was completed.”
- **Strategy:** “Use priority-scoring algorithm A or B for this task?”
- **State:** “Is this task NEW or DONE, and which operations are allowed?”

A handler may process a Command, change State, then publish an Event. These mechanisms work together, but they are not interchangeable.

## 9. Using Command in Real Applications

### 9.1. Desktop UI and Menus

Actions such as Save, Undo, Redo, and Delete Selection may appear on toolbar buttons, context menus, and keyboard shortcuts. Different Invokers can create/execute the same Command type without duplicating business logic.

This fits naturally with **JavaFX** or **Swing**: UI handlers convert user intent into commands while Receivers/services execute them. In very small applications, direct action callbacks may still be clearer than introducing several layers.

### 9.2. Backend Services and CQRS

In a Java/Spring backend, an application service can serve as a command handler:

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

This is an **architectural sketch** because **InvoiceRepository** and invoice business rules have not been defined. It illustrates a common variation: a **Command as an immutable DTO**, with a **Handler** performing business logic, rather than a Command object holding a Receiver and exposing **execute()**. Both encapsulate requests but have different trade-offs.

**CQRS** (Command Query Responsibility Segregation) separates state-changing operations from data queries; it does not require a command bus, event sourcing, or two databases in every project. Clear command handlers can also help in ordinary architectures.

### 9.3. Transactions, Concurrency, and Authorization

With concurrent requests:

- Enforce **authorization** for the actor, resource, and operation on the server. Never allow clients to supply arbitrary class names or payloads to invoke arbitrary methods.
- Use **version/optimistic locking** or conditional updates so concurrent commands do not overwrite each other.
- Define each Command **transaction** boundary; an in-memory history stack does not replace a transaction.
- If audit is required, record command identity, actor, timestamp, resources, results, and error details under an appropriate security policy; avoid unnecessary sensitive data.
- If a Command creates side effects beyond the database, consider **outbox**, idempotency, saga/compensation, and operational recovery policies.

**UI undo history must not be treated as a way to cancel a real payment transaction.** Once a change takes effect externally, undo requires a clearly defined compensating business operation with auditability and appropriate authorization.

## 10. When to Use Command and When to Avoid It

**Consider Command when:**

- The same operation originates from several places and needs a consistent execution contract.
- You need **undo/redo**, macros, history, or controlled replay.
- Requests need to be queued, scheduled, audited, or processed with retry/idempotency policies.
- You want to separate business handlers from UI, controllers, schedulers, or transport mechanisms.
- You want operations represented as independently testable objects with explicit identity and data.

**Do not use Command simply because every operation is a function.** A pure **calculateTotal()**, small internal helper, or button callback with no special lifecycle/management needs may not need a Command class, Manager, and factory.

If you merely need to defer a callback within one process, **Runnable** may suffice:

~~~java
Runnable task = () -> System.out.println("Đã thực thi");
task.run();
~~~

Command Pattern becomes valuable when beyond “execute later,” the request requires **business meaning, parameters, lifecycle, history, error control, or execution policies** to be made explicit.

### Common Pitfalls

| Mistake | Effect | Remedy |
| --- | --- | --- |
| Command contains UI code, DB queries, email sending, and unrelated rules | God object, difficult to test | Keep business logic in Receiver/service; Command retains intent and parameters |
| Undo always “sets the flag to false” regardless of previous value | Corrupts prior state | Save the previous value or a correct inverse operation |
| History stack is popped before knowing undo succeeded | Loses commands on failure | Update stacks only after successful operations |
| Reuse an active Command instance | Unintended repeated execution | Specify each Command lifecycle and state |
| Retry side-effectful commands without idempotency | Duplicate sends, writes, or charges | Command ID plus suitable guards/transactions |
| Treat an in-memory command object as a durable message | Receiver/dependencies cannot be serialized | Use request DTOs/handlers and versioned schemas |
| Share undo history across unrelated users | One user can affect another user history | Partition by session/user/resource and enforce authorization |
| Use Command for every trivial operation | Boilerplate and extra layers | Keep direct methods/lambdas when sufficiently clear |

## 11. Practical Exercise

Design a simple Java text editor with **TextDocument** as Receiver and **CommandManager** as Invoker.

Required commands:

1. **AppendTextCommand(text):** append text to the document; undo removes only the inserted text at its correct position.
2. **ReplaceTextCommand(from, to):** replace the first matching segment; store sufficient information for exact undo.
3. **ClearDocumentCommand:** remove all content, optionally saving a pre-clear snapshot for restoration.
4. Support multistep undo/redo, clearing redo history when a new command executes.

**Recommended test cases:** append twice, then undo/redo; replace with no match; clear then restore accented Unicode; failed commands must not enter history; edits outside the manager should be rejected or reported as explicit conflicts.

Try extending it: store a Command as a DTO with **commandId** and **expectedVersion**, applying it to a document persisted in a database. Distinguish serializable data from Receiver/runtime services. If two users edit the same document, explain conflict detection/handling rather than trusting an in-memory undo stack.

**Acceptance criteria:** clients submit Commands through one contract; Receiver owns editing logic; history changes only after operations complete; undo/redo preserve data; tests cover valid paths, failures, and conflicts.

**Remember:** Command Pattern encapsulates **the intent to perform an action** so a request can be passed, managed, and processed through one interface. It decouples Invokers from Receivers, while undo, retry, history persistence, authorization, and data consistency still require explicit design around the real business operation.
