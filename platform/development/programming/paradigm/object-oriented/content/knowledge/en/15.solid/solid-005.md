# Interface Segregation: Contracts Tailored to Clients (Interface Segregation Principle — ISP)

> **Context:** SOLID in object-oriented design. **Key idea:** A client should depend only on the operations it actually needs.

## 1. What Problem Does ISP Solve?

The **Interface Segregation Principle (ISP)** is often stated as: *Clients should not be forced to depend upon interfaces that they do not use*. Clients should not depend on unnecessary methods.

In Java, a **client** is a class, service, or module calling through a contract, not necessarily an end user. Here, **interface** means a programming contract, represented by a Java interface or abstract class. An overly broad contract (*fat interface*) forces very different clients to see the same operations.

For example, a document-management application has three distinct needs:

| Client | Actual need | Contract it should know |
| --- | --- | --- |
| Document download service | Read by ID | **DocumentReader** |
| Document import job | Save documents | **DocumentWriter** |
| Data cleanup job | Delete according to policy | **DocumentDeleter** |
| Read-only archive | Provide data for lookup | Only needs to implement **DocumentReader** |

If every client depends on **DocumentStorage** exposing read, write, and delete, the application creates unnecessary dependencies. A read-only archive may even be forced to declare operations it cannot support.

### Signs of an ISP Violation

- A class implements numerous methods only to throw **UnsupportedOperationException**, return fake values, or do nothing.
- A client uses 1–2 methods but must mock/stub a contract with dozens of methods for testing.
- Adding a feature needed by one client group forces changes to classes in another group.
- Different permission levels (read-only, write-only, admin) are all given the same unrestricted API.

**Important distinction:** An interface with many methods is *not automatically* wrong. The problem arises when client groups with different needs must depend on unrelated operations.

## 2. Initial Design: An Overly Broad Contract

Suppose every document store must support three operations:

~~~java
import java.util.Map;
import java.util.Optional;

interface DocumentStorage {
    Optional<String> findById(String id);
    void save(String id, String content);
    void delete(String id);
}

final class ReadOnlyArchive implements DocumentStorage {
    private final Map<String, String> snapshot = Map.of("A1", "Biên bản");

    @Override
    public Optional<String> findById(String id) {
        return Optional.ofNullable(snapshot.get(id));
    }

    @Override
    public void save(String id, String content) {
        throw new UnsupportedOperationException("Kho chỉ đọc");
    }

    @Override
    public void delete(String id) {
        throw new UnsupportedOperationException("Kho chỉ đọc");
    }
}
~~~

**Problem:** **ReadOnlyArchive** can only read, but **DocumentStorage** claims the object also supports writing and deletion. Clients can legitimately compile calls to **save/delete** but encounter failures at runtime. This also raises a **Liskov Substitution Principle (LSP)** concern: the implementation cannot fulfill expectations established by the broad contract.

Do not patch this by returning false success, adding no-op methods, or using **default methods** to conceal a missing capability. Narrow contracts according to client needs.

## 3. Redesigning with ISP: Small, Purposeful Contracts

Place the following code in **IspDemo.java**. It compiles and runs independently with **Java 17+**. Each interface describes a capability. **InMemoryStore** provides all three capabilities, while **ReadOnlyArchive** only provides reading. Clients receive exactly the contracts they need.

~~~java
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class IspDemo {

    // Hợp đồng dành cho client chỉ cần đọc.
    interface DocumentReader {
        Optional<String> findById(String id);
    }

    // Hợp đồng dành cho client cần nhập hoặc cập nhật.
    interface DocumentWriter {
        void save(String id, String content);
    }

    // Hợp đồng dành cho công việc dọn dữ liệu.
    interface DocumentDeleter {
        void delete(String id);
    }

    // Một adapter được phép hỗ trợ nhiều hợp đồng.
    static final class InMemoryStore
            implements DocumentReader, DocumentWriter, DocumentDeleter {
        private final Map<String, String> data = new ConcurrentHashMap<>();

        @Override
        public Optional<String> findById(String id) {
            return Optional.ofNullable(data.get(id));
        }

        @Override
        public void save(String id, String content) {
            data.put(Objects.requireNonNull(id),
                     Objects.requireNonNull(content));
        }

        @Override
        public void delete(String id) {
            data.remove(id);
        }
    }

    // Không cần triển khai phương thức ghi/xóa giả.
    static final class ReadOnlyArchive implements DocumentReader {
        private final Map<String, String> snapshot;

        ReadOnlyArchive(Map<String, String> source) {
            this.snapshot = Map.copyOf(source);
        }

        @Override
        public Optional<String> findById(String id) {
            return Optional.ofNullable(snapshot.get(id));
        }
    }

    static final class DownloadService {
        private final DocumentReader reader;

        DownloadService(DocumentReader reader) {
            this.reader = Objects.requireNonNull(reader);
        }

        String download(String id) {
            return reader.findById(id)
                    .orElseThrow(() -> new NoSuchElementException(id));
        }
    }

    static final class ImportService {
        private final DocumentWriter writer;

        ImportService(DocumentWriter writer) {
            this.writer = Objects.requireNonNull(writer);
        }

        void importFile(String id, String content) {
            writer.save(id, content);
        }
    }

    public static void main(String[] args) {
        InMemoryStore mainStore = new InMemoryStore();

        new ImportService(mainStore).importFile("D01", "Hợp đồng mới");
        System.out.println(
                new DownloadService(mainStore).download("D01"));

        DocumentReader archive =
                new ReadOnlyArchive(Map.of("A01", "Bản lưu năm trước"));
        System.out.println(
                new DownloadService(archive).download("A01"));
    }
}
~~~

Run:

~~~bash
javac IspDemo.java
java IspDemo
~~~

Output:

~~~text
Hợp đồng mới
Bản lưu năm trước
~~~

**Key observations from the example:**

1. **DownloadService** knows only **DocumentReader**. It cannot see the deletion API even if the underlying object supports deletion.
2. **ImportService** knows only **DocumentWriter**. It receives **InMemoryStore** but cannot assume read or delete capabilities.
3. **ReadOnlyArchive** needs no unsupported methods because its contract reflects its actual capabilities.
4. A class may **implement** multiple interfaces when it genuinely provides multiple capabilities. ISP does not require a separate class for each interface.
5. **Optional.empty()** indicates a missing document, not a network, authorization, or system error; such failures require appropriate error mechanisms.

For maintainable production applications, put each interface and business class in appropriate files/packages. The types are nested inside **IspDemo** only to make the example immediately runnable.

## 4. Dependency Diagram After Segregation

~~~mermaid
classDiagram
    class DocumentReader {
        <<interface>>
        +findById(id) Optional~String~
    }
    class DocumentWriter {
        <<interface>>
        +save(id, content) void
    }
    class DocumentDeleter {
        <<interface>>
        +delete(id) void
    }
    class DownloadService
    class ImportService
    class InMemoryStore
    class ReadOnlyArchive

    DownloadService --> DocumentReader : uses
    ImportService --> DocumentWriter : uses
    DocumentReader <|.. InMemoryStore
    DocumentWriter <|.. InMemoryStore
    DocumentDeleter <|.. InMemoryStore
    DocumentReader <|.. ReadOnlyArchive
~~~

Arrows from a **Service** to an **interface** represent client-side dependencies; **implements** arrows show capabilities provided by adapters. Each client can switch implementations without receiving methods outside its needs.

## 5. More Focused Testing

With **JUnit 5**, we can supply minimal implementations to each client. **DocumentReader** and **DocumentWriter** each have one abstract method, so lambdas may be appropriate.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class IspDemoTest {

    @Test
    void taiTaiLieuTuKhoChiDoc() {
        var archive =
                new IspDemo.ReadOnlyArchive(Map.of("A1", "Bản lưu"));
        var service = new IspDemo.DownloadService(archive);

        assertEquals("Bản lưu", service.download("A1"));
    }

    @Test
    void nhapTaiLieuChiCanHopDongGhi() {
        AtomicReference<String> recorded = new AtomicReference<>();
        IspDemo.DocumentWriter writer =
                (id, content) -> recorded.set(id + ":" + content);

        var service = new IspDemo.ImportService(writer);
        service.importFile("D1", "Nội dung");

        assertEquals("D1:Nội dung", recorded.get());
    }
}
~~~

The first test confirms that a reading client works with a read-only archive. The second tests a writing client without stubs for read/delete. In Spring applications, the same principle applies when injecting only the needed interfaces into each **@Service**; **@Component/@Repository** adapters may implement multiple contracts. If multiple beans implement the same interface, select them using **@Qualifier**, **@Primary**, or suitable configuration.

## 6. Distinguishing ISP from Related Principles

| Principle | Design question | Connection to the example |
| --- | --- | --- |
| **ISP** — Interface Segregation | Does a client depend on methods it does not need? | DownloadService receives only DocumentReader. |
| **SRP** — Single Responsibility | How many independent reasons to change does a module have? | Document download and import logic live in separate services when their responsibilities differ. |
| **DIP** — Dependency Inversion | Does business code depend on suitable abstractions instead of storage details? | DownloadService depends on DocumentReader, not InMemoryStore. |
| **LSP** — Liskov Substitution | Does an implementation honor its contract? | ReadOnlyArchive does not claim write/delete capabilities only to throw when called. |

These principles complement but do not replace one another. Using an interface instead of a concrete class does not satisfy ISP if the interface remains too broad.

## 7. Designing Contract Boundaries in Real Projects

There is no "one method per interface" rule. Split contracts according to **client roles, capabilities, and reasons to change**.

| Scenario | Sensible decision | Rationale |
| --- | --- | --- |
| Every client always needs the same cohesive set of operations | Keep one concise, consistent interface | Avoids creating too many meaningless types. |
| Viewers only read; synchronization jobs only write | Separate **Reader** and **Writer** | Clients see only the capabilities they need. |
| One adapter supports every role | Let it implement multiple interfaces | Avoids duplicating logic or instances. |
| An administrative client truly needs all capabilities | A composite interface may fit that client | For example, **DocumentAdmin extends DocumentReader, DocumentWriter, DocumentDeleter**. |
| An operation always throws **UnsupportedOperationException** because it is unsupported | Revisit the contract's promise | The interface may cover too many capabilities. |

In REST/Spring systems, separating Java interfaces **does not automatically enforce security authorization**. Giving a client only **DocumentReader** limits its compile-time/design API; write/delete endpoints still require authentication, authorization, and business-rule checks at system boundaries.

### Safely Refactoring a Large Interface

1. **Map clients:** Document which methods each client calls and which behavior groups change together.
2. **Define small contracts:** Name interfaces after meaningful domain capabilities, such as **DocumentReader** and **DocumentWriter**.
3. **Migrate dependencies gradually:** Update each client's constructors, fields, and tests to use the relevant interface; let existing adapters implement only the contracts they support.
4. **Handle the old contract:** Remove the old interface only when it has no consumers; for public libraries, consider source/binary compatibility and a migration plan.
5. **Verify behavior:** Do not sacrifice semantics (not-found errors, access rights, data consistency) merely to shorten interfaces.

**Common ISP mistakes:**

- Mechanically splitting interfaces method by method, making the API harder to navigate.
- Creating many interfaces but still injecting one composite interface into clients.
- Hiding a "God Service" behind multiple interfaces without improving real dependencies or responsibilities; ISP reduces client coupling but does not automatically solve all implementation problems.
- Mistaking a read-only Java interface for runtime authorization.

## 8. Practice Exercise

A notification system has a **NotificationService** contract with **sendEmail()**, **sendSms()**, and **sendPush()**. One job only sends email, while another adapter supports only SMS.

Design interfaces for the client groups (**EmailSender**, **SmsSender**, **PushSender**), write an **OtpService** that only depends on SMS sending, and create a fake **SmsSender** for tests. Then ask:

- Must an SMS-only adapter declare fake email/push methods?
- Can **OtpService** see and accidentally call **sendEmail()**?
- If one provider supports both email and SMS, can it implement both interfaces without duplicating the provider?
- If a chat channel is added later, must SMS-only clients change?

**Success criterion:** Client-facing contracts expose only operations clients genuinely need, and every implementation correctly performs all operations it advertises. That is the practical value of the **Interface Segregation Principle**.
