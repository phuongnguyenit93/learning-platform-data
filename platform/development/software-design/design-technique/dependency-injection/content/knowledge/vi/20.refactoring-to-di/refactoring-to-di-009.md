# Chuyển vòng đời và quyền đóng tài nguyên mà không làm thay đổi hành vi

Khi refactor mã Java sang **Dependency Injection (DI)**, thao tác thường thấy là chuyển `new SomeClient(...)` ra khỏi một service và truyền `SomeClient` vào constructor. Về mặt cấu trúc, service đã nhận collaborator từ bên ngoài. Nhưng nếu service cũ **tự tạo và tự đóng client**, còn phiên bản mới chỉ được inject client mà vẫn gọi `client.close()`, thay đổi đó có thể gây lỗi nghiêm trọng: một service vô tình đóng tài nguyên mà nhiều service khác cũng đang dùng.

Ngược lại, nếu sau refactor **không ai đóng client nữa**, chương trình có thể rò socket, connection pool, file descriptor hoặc thread. Cùng một phép tính nghiệp vụ có thể trả kết quả đúng trong bài kiểm thử đơn giản nhưng ứng dụng lại hỏng sau vài request hoặc khi shutdown.

Bài học trong chương **Refactor sang DI** tập trung vào một mục tiêu cụ thể:

> **Di chuyển trách nhiệm tạo, sở hữu và giải phóng tài nguyên tới đúng ranh giới vòng đời, trong khi giữ nguyên hành vi quan sát được của use case và các cam kết tài nguyên vốn có.**

Ta sẽ thực hành bằng Java 17 thuần, dùng **constructor injection**, **composition root**, `AutoCloseable`, `try-with-resources` và fake ghi sự kiện. Sau đó mới liên hệ với quản lý scope và vòng đời trong DI container.

## 1. Vì sao chỉ thay `new` bằng constructor injection là chưa đủ?

Giả sử `ReportExporter` ghi báo cáo vào một hệ thống lưu trữ. Phiên bản cũ tự tạo client:

```java
// Phác họa mã trước refactor.
final class ReportExporter implements AutoCloseable {
    private final StorageClient client;

    ReportExporter(StorageSettings settings) {
        this.client = new StorageClient(settings);
    }

    void export(Report report) {
        try (StorageSession session = client.openSession()) {
            session.write(report);
        }
    }

    @Override
    public void close() {
        client.close();
    }
}
```

Ở phiên bản cũ, service thực hiện **hai vai trò**:

- **Consumer:** dùng `StorageClient` để mở session và xuất báo cáo.
- **Owner:** tạo `StorageClient` và chịu trách nhiệm gọi `close()` khi kết thúc.

Một thay đổi nửa chừng dễ mắc phải:

```java
// Phản ví dụ: client được inject nhưng service vẫn tự đóng.
final class ReportExporter implements AutoCloseable {
    private final StorageClient client;

    ReportExporter(StorageClient client) {
        this.client = Objects.requireNonNull(client);
    }

    void export(Report report) {
        // Sử dụng client...
    }

    @Override
    public void close() {
        client.close(); // Ai bảo đảm service sở hữu client này?
    }
}
```

Nếu composition root cấp **cùng một client** cho `ReportExporter` và `AuditWriter`, đóng exporter có thể làm audit writer mất kết nối. Một biến thể nguy hiểm khác là bỏ `close()` khỏi exporter nhưng composition root không đóng client. Cả hai đều là thay đổi hành vi vận hành, dù phần logic xuất báo cáo không đổi.

**DI không tự chuyển quyền sở hữu.** Constructor injection chỉ cho biết service nhận một collaborator; ai có quyền đóng tài nguyên phải được xác định bằng hợp đồng rõ ràng.

## 2. Phân biệt owner, consumer, borrower và scope

| Khái niệm | Trách nhiệm chính | Ví dụ |
|---|---|---|
| **Owner (chủ sở hữu)** | Quản lý toàn bộ thời gian sống của tài nguyên; đóng khi hết hạn và cleanup nếu khởi động thất bại | Composition root tạo và đóng storage client |
| **Consumer (bên sử dụng)** | Gọi hành vi của collaborator đã nhận; không mặc nhiên được đóng collaborator | `ReportExporter` gọi `client.openSession()` |
| **Borrower (bên mượn)** | Sử dụng tài nguyên trong phạm vi được cấp; tuân thủ quy tắc trả lại/kết thúc | Một transaction mượn connection từ pool |
| **Scope (ranh giới sử dụng)** | Quy định instance được chia sẻ trong bao lâu và khi nào kết thúc | Application, request, transaction |
| **Lifecycle boundary** | Điều phối tạo, sẵn sàng, dừng nhận việc và giải phóng | `main`, startup coordinator, request boundary |

Tại mọi điểm refactor, hãy hỏi **hai câu riêng**:

1. **Đối tượng nào cần tài nguyên để thực thi nghiệp vụ?** Đó là consumer và mối quan hệ cần thể hiện qua constructor hoặc method.
2. **Ai đảm bảo tài nguyên được giải phóng đúng một lần và đúng thời điểm?** Đó là owner theo hợp đồng hoặc cơ chế quản lý scope.

Một service có thể **sở hữu session do chính nó mở trong một lời gọi**, đồng thời chỉ **mượn client dùng chung được inject**. Không có mâu thuẫn: ownership có thể khác nhau giữa các cấp tài nguyên.

## 3. Bảng bất biến phải giữ trước và sau refactor

“Không thay đổi hành vi” cần được cụ thể hóa. Chỉ so sánh giá trị trả về là chưa đủ.

| Bất biến cần bảo toàn | Câu hỏi kiểm chứng |
|---|---|
| **Kết quả nghiệp vụ** | Cùng đầu vào thì trả cùng kết quả hoặc lỗi theo hợp đồng hiện hành? |
| **Side effect** | Số lần ghi/gửi/cập nhật và thứ tự của chúng có thay đổi không? |
| **Thời điểm cấp tài nguyên** | Client vẫn được tạo một lần cho một phiên ứng dụng hay vô tình tạo mỗi request? |
| **Phạm vi dùng session** | Mỗi thao tác vẫn mở session riêng và kết thúc đúng lúc? |
| **Thứ tự đóng** | Consumer ngừng sử dụng trước khi dependency bị đóng? |
| **Lỗi và cleanup** | Khi ghi thất bại, session vẫn đóng; khi startup lỗi, client đã mở được dọn? |
| **Không đóng nhầm tài nguyên dùng chung** | Một consumer kết thúc có làm consumer khác mất client không? |
| **Thread safety** | Việc chia sẻ mới có làm lộ state mutable giữa các request không? |
| **Tương thích API** | Caller vốn gọi `close()` hoặc dùng `try-with-resources` có cần được di chuyển đúng cách không? |

Đây là **characterization tests**: các phép thử ghi nhận hành vi hiện hữu để làm mốc cho refactor. Chúng không chứng minh mọi hành vi cũ đều đúng hoặc mong muốn. Nếu mã cũ đang rò tài nguyên, việc sửa leak là một thay đổi có chủ ý cần được ghi nhận và kiểm thử riêng, thay vì tuyên bố “hoàn toàn không đổi”.

### Đồ thị trước và sau

```text
Trước:

main
  └── LegacyReportExporter
          ├── tự new StorageClient      [owner]
          ├── open StorageSession       [owner của session]
          └── close StorageClient


Sau:

main / composition root            [owner của client]
  ├── new StorageClient
  ├── new ReportExporter(client)    [consumer của client]
  │       └── open StorageSession   [owner của session theo mỗi lần gọi]
  └── close StorageClient khi ứng dụng kết thúc
```

Bản refactor đúng không chỉ chuyển vị trí dòng `new`; nó chuyển **quyền và trách nhiệm đóng client** sang composition root, đồng thời **giữ session là tài nguyên theo lời gọi**.

## 4. Quy trình refactor an toàn theo từng bước

Thay vì thay toàn bộ graph trong một lần, hãy thực hiện từng thay đổi nhỏ.

### Bước 1 — Khoanh vùng tài nguyên và nơi gọi `close()`

Đọc code đang có và lập một bảng:

| Tài nguyên | Được tạo tại đâu? | Ai dùng? | Hiện ai đóng? | Scope thực tế |
|---|---|---|---|---|
| `StorageClient` | Constructor exporter | Exporter | Exporter.close() | Một phiên exporter |
| `StorageSession` | Bên trong `export(...)` | Một lần xuất | `try-with-resources` | Một lời gọi |
| `ExecutorService` nếu có | `main` hoặc factory | Nhiều client/worker | Startup/shutdown coordinator | Ứng dụng |
| Connection mượn từ pool | `DataSource.getConnection()` | Transaction | Scope transaction | Một đơn vị công việc |

Hãy xác nhận client cũ được **tạo mỗi request, mỗi service instance hay một lần cho toàn ứng dụng**. Nếu ngay lúc refactor đổi từ “mỗi service một client” sang “các service cùng chia sẻ một client”, đó là một quyết định mới về scope và concurrency, cần kiểm thử độc lập.

### Bước 2 — Ghi lại hành vi hiện hữu

Chụp lại:

- API đầu vào, đầu ra và kiểu lỗi.
- Thứ tự `client.open` → `session.open` → `write` → `session.close` → `client.close` ở đường thành công.
- Đường lỗi khi `write` ném exception.
- Số lần mở/đóng trên nhiều lời gọi.
- Vấn đề nếu đóng một resource khi consumer khác còn dùng.

Nên dùng fake/event log thay vì yêu cầu network thật, giúp kiểm thử nhanh và ổn định.

### Bước 3 — Tách sử dụng khỏi việc tạo

Thay constructor nhận settings rồi tự `new` client bằng constructor nhận `StorageClient`:

```java
final class ReportExporter {
    private final StorageClient client;

    ReportExporter(StorageClient client) {
        this.client = Objects.requireNonNull(client, "client");
    }

    // Các thao tác nghiệp vụ vẫn dùng client như trước.
}
```

Không thay thuật toán xuất báo cáo cùng lúc. Chỉ thay **đường cấp collaborator**.

### Bước 4 — Chuyển quyền đóng client sang owner mới

Composition root hoặc một `Application` được root tạo ra sở hữu client:

```java
StorageClient client = createStorageClient(settings);
ReportExporter exporter = new ReportExporter(client);

// Khi dừng ứng dụng: trước tiên ngừng mọi lời gọi exporter,
// sau đó chủ sở hữu mới gọi client.close().
```

Đối tượng được inject vào exporter được xem là **borrowed dependency**. Exporter không được tự đóng client. Nếu caller bên ngoài trước đây gọi `exporter.close()`, cần có kế hoạch chuyển điểm đóng về **owner** mới hoặc giữ một façade tương thích trong giai đoạn di chuyển.

### Bước 5 — Giữ nguyên scope của session mỗi lời gọi

```java
String export(String reportId) {
    try (StorageSession session = client.openSession()) {
        session.write(reportId);
        return "EXPORTED " + reportId;
    }
}
```

Session được tạo lúc xử lý, không phải lúc xây exporter. `try-with-resources` đóng session kể cả khi `write(...)` ném exception.

### Bước 6 — Bảo vệ trường hợp startup thất bại

Nếu root tạo client rồi gặp lỗi khi tạo một service khác, nó phải đóng client đã tạo. Nếu client factory mở dở socket nhưng **chưa trả client thành công**, factory chịu trách nhiệm dọn phần cấp phát dở của chính nó.

### Bước 7 — So sánh hành vi bằng test, rồi mới mở rộng graph

Sau khi hai phiên bản trả cùng kết quả và có cùng chuỗi sự kiện cần thiết, mới xét tối ưu chia sẻ client, thêm pool, đổi timeout, sửa retry hoặc chuyển sang DI container. Những thay đổi này **có thể làm đổi hành vi** và không nên trộn vào cùng bản refactor cấu trúc.

## 5. Ví dụ Java 17 hoàn chỉnh: chuyển owner nhưng giữ hành vi

Ví dụ xây một client giả ghi chuỗi sự kiện. Nó có hai tầng tài nguyên:

- `StorageClient` sống suốt một phiên sử dụng ứng dụng.
- `StorageSession` được mở và đóng **theo mỗi lần xuất báo cáo**.

Có hai cách lắp ghép dùng chung một logic xuất báo cáo:

- `LegacyReportExporter` tự tạo và sở hữu client (trước refactor).
- `ReportExporter` chỉ nhận client qua constructor; `Application` sở hữu và đóng client (sau refactor).

Lưu toàn bộ mã dưới đây thành `OwnershipRefactorDemo.java` (Java 17 trở lên):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class OwnershipRefactorDemo {

    // Fake ghi lại thứ tự sự kiện; ví dụ chạy tuần tự.
    static final class Trace {
        private final List<String> events = new ArrayList<>();

        void add(String event) {
            events.add(event);
        }

        List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    interface StorageSession extends AutoCloseable {
        void write(String reportId);

        @Override
        void close();
    }

    interface StorageClient extends AutoCloseable {
        StorageSession openSession();

        @Override
        void close();
    }

    static final class TracedStorageClient implements StorageClient {
        private final Trace trace;
        private final boolean failOnWrite;
        private boolean closed;

        TracedStorageClient(Trace trace, boolean failOnWrite) {
            this.trace = Objects.requireNonNull(trace, "trace");
            this.failOnWrite = failOnWrite;
            trace.add("client.open");
        }

        @Override
        public StorageSession openSession() {
            if (closed) {
                throw new IllegalStateException("client is closed");
            }
            trace.add("session.open");

            return new StorageSession() {
                private boolean sessionClosed;

                @Override
                public void write(String reportId) {
                    if (sessionClosed) {
                        throw new IllegalStateException(
                            "session is closed");
                    }

                    trace.add("write " + reportId);
                    if (failOnWrite) {
                        throw new IllegalStateException("write failed");
                    }
                }

                @Override
                public void close() {
                    if (!sessionClosed) {
                        sessionClosed = true;
                        trace.add("session.close");
                    }
                }
            };
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                trace.add("client.close");
            }
        }
    }

    // Logic xuất báo cáo được giữ nguyên trong cả hai nhánh.
    static String writeReport(
            StorageClient client, String reportId) {
        Objects.requireNonNull(client, "client");
        if (reportId == null || reportId.isBlank()) {
            throw new IllegalArgumentException(
                "reportId must not be blank");
        }

        try (StorageSession session = client.openSession()) {
            session.write(reportId);
            return "EXPORTED " + reportId;
        }
    }

    // Trước: exporter tự tạo và tự đóng client.
    static final class LegacyReportExporter implements AutoCloseable {
        private final StorageClient ownedClient;

        LegacyReportExporter(Trace trace, boolean failOnWrite) {
            this.ownedClient = new TracedStorageClient(
                trace, failOnWrite);
        }

        String export(String reportId) {
            return writeReport(ownedClient, reportId);
        }

        @Override
        public void close() {
            ownedClient.close();
        }
    }

    // Sau: exporter nhận một client được mượn, KHÔNG đóng nó.
    static final class ReportExporter {
        private final StorageClient client;

        ReportExporter(StorageClient client) {
            this.client = Objects.requireNonNull(
                client, "client");
        }

        String export(String reportId) {
            return writeReport(client, reportId);
        }
    }

    // Owner ở cấp ứng dụng.
    static final class Application implements AutoCloseable {
        private final ReportExporter exporter;
        private final StorageClient ownedClient;
        private boolean closed;

        Application(
                ReportExporter exporter,
                StorageClient ownedClient) {
            this.exporter = Objects.requireNonNull(exporter);
            this.ownedClient = Objects.requireNonNull(ownedClient);
        }

        String export(String reportId) {
            // Client từ chối lời gọi sau khi bị đóng.
            return exporter.export(reportId);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                ownedClient.close();
            }
        }
    }

    // Composition root: tạo, lắp, bàn giao owner.
    static Application bootstrap(
            Trace trace,
            boolean failOnWrite,
            boolean failAfterClientCreation) {

        StorageClient client =
            new TracedStorageClient(trace, failOnWrite);

        try {
            // Mô phỏng lỗi khi lắp phần tiếp theo của graph.
            if (failAfterClientCreation) {
                throw new IllegalStateException("startup failed");
            }

            ReportExporter exporter = new ReportExporter(client);
            return new Application(exporter, client);

        } catch (RuntimeException | Error startupFailure) {
            // Root vẫn là owner khi việc bàn giao chưa hoàn tất.
            try {
                client.close();
            } catch (RuntimeException | Error cleanupFailure) {
                if (cleanupFailure != startupFailure) {
                    startupFailure.addSuppressed(cleanupFailure);
                }
            }
            throw startupFailure;
        }
    }

    public static void main(String[] args) {
        Trace before = new Trace();
        String oldResult;

        try (LegacyReportExporter exporter =
                 new LegacyReportExporter(before, false)) {
            oldResult = exporter.export("REP-7");
        }

        Trace after = new Trace();
        String newResult;

        try (Application app =
                 bootstrap(after, false, false)) {
            newResult = app.export("REP-7");
        }

        System.out.println("old=" + oldResult);
        System.out.println("new=" + newResult);
        System.out.println(
            "same-events=" +
            before.snapshot().equals(after.snapshot()));
        System.out.println("events=" + after.snapshot());
    }
}
```

Biên dịch và chạy:

```bash
javac OwnershipRefactorDemo.java
java OwnershipRefactorDemo
```

Kết quả dự kiến:

```text
old=EXPORTED REP-7
new=EXPORTED REP-7
same-events=true
events=[client.open, session.open, write REP-7, session.close, client.close]
```

Kết quả chứng minh rằng việc chuyển owner **không cần đổi kết quả nghiệp vụ hoặc thời điểm đóng session**. Đến khi cả hai phiên đã hoàn tất, client đều được đóng một lần.

### Chính xác điều gì thay đổi?

Trong `LegacyReportExporter`, constructor tạo `TracedStorageClient`, rồi `close()` của exporter trực tiếp đóng client. Vì vậy, **exporter vừa là consumer vừa là owner**.

Ở phiên bản mới, `ReportExporter` nhận `StorageClient` qua constructor và **không có `close()`**. `bootstrap(...)` tạo client và chuyển quyền quản lý thành công cho `Application`. `Application.close()` đóng client.

Điểm đáng chú ý là sau refactor **không hề đổi**:

- `writeReport(...)` vẫn kiểm tra `reportId` trước khi mở session.
- Mỗi `export(...)` vẫn mở đúng một session và đóng khi kết thúc.
- Lỗi `write failed` vẫn có thể truyền ra caller.
- Client vẫn sống từ lúc tạo exporter/app đến lúc owner đóng nó.

Ví dụ chủ ý để **cùng helper `writeReport(...)`** phục vụ hai phiên nhằm cô lập thay đổi ownership. Trong mã thực tế, hãy dùng characterization tests để so sánh đường xử lý hiện hữu, thay vì đồng thời viết lại nghiệp vụ.

### Điều gì *chưa* được phép suy ra từ ví dụ?

`TracedStorageClient` là fake; nó không có socket hay pool thật. Hai phiên có chuỗi sự kiện giống nhau **không chứng minh** một SDK production sẽ an toàn khi chia sẻ giữa nhiều thread hoặc chịu đóng khi request đang chạy.

`Trace` dùng `ArrayList` và các cờ `boolean` để code dễ hiểu; chương trình chạy tuần tự. Với ứng dụng xử lý nhiều request đồng thời, cần thiết kế đồng bộ và shutdown/drain riêng trước khi đổi phạm vi chia sẻ client.

## 6. Kiểm thử hành vi trước/sau trên cả đường lỗi

Một phép thử “happy path” chỉ chứng minh một lần xuất thành công. Refactor quyền sở hữu cần kiểm tra thêm **đường lỗi, nhiều lần gọi và startup thất bại**.

Lưu chương trình sau thành `OwnershipRefactorCheck.java` cạnh file demo:

```java
import java.util.List;

public final class OwnershipRefactorCheck {

    private static void expect(
            List<String> actual, List<String> expected) {
        if (!actual.equals(expected)) {
            throw new AssertionError(
                "Expected " + expected + " but got " + actual);
        }
    }

    public static void main(String[] args) {
        // 1. Đường thành công: trước và sau có cùng thứ tự sự kiện.
        var before = new OwnershipRefactorDemo.Trace();
        String oldResult;

        try (var old = new OwnershipRefactorDemo
                .LegacyReportExporter(before, false)) {
            oldResult = old.export("R1");
        }

        var after = new OwnershipRefactorDemo.Trace();
        String newResult;

        try (var app = OwnershipRefactorDemo
                .bootstrap(after, false, false)) {
            newResult = app.export("R1");
        }

        if (!oldResult.equals(newResult)) {
            throw new AssertionError("Business result changed");
        }

        List<String> success = List.of(
            "client.open",
            "session.open",
            "write R1",
            "session.close",
            "client.close"
        );

        expect(before.snapshot(), success);
        expect(after.snapshot(), success);

        // 2. Khi write lỗi, session và client vẫn được đóng.
        var oldFailure = new OwnershipRefactorDemo.Trace();
        boolean oldFailed = false;

        try (var old = new OwnershipRefactorDemo
                .LegacyReportExporter(oldFailure, true)) {
            old.export("R2");
        } catch (IllegalStateException expected) {
            oldFailed = "write failed".equals(
                expected.getMessage());
        }

        var newFailure = new OwnershipRefactorDemo.Trace();
        boolean newFailed = false;

        try (var app = OwnershipRefactorDemo
                .bootstrap(newFailure, true, false)) {
            app.export("R2");
        } catch (IllegalStateException expected) {
            newFailed = "write failed".equals(
                expected.getMessage());
        }

        if (!oldFailed || !newFailed) {
            throw new AssertionError(
                "Write failure was changed or swallowed");
        }

        List<String> error = List.of(
            "client.open",
            "session.open",
            "write R2",
            "session.close",
            "client.close"
        );
        expect(oldFailure.snapshot(), error);
        expect(newFailure.snapshot(), error);

        // 3. Hai lời gọi dùng chung client, session vẫn tách biệt.
        var multiple = new OwnershipRefactorDemo.Trace();

        var app = OwnershipRefactorDemo
            .bootstrap(multiple, false, false);

        try {
            if (!"EXPORTED R3".equals(app.export("R3"))
                    || !"EXPORTED R4".equals(app.export("R4"))) {
                throw new AssertionError("Wrong result");
            }
        } finally {
            app.close();
        }
        app.close(); // Hợp đồng idempotent của Application mẫu.

        expect(multiple.snapshot(), List.of(
            "client.open",
            "session.open",
            "write R3",
            "session.close",
            "session.open",
            "write R4",
            "session.close",
            "client.close"
        ));

        // 4. Refactor không được làm mất đường cleanup khi startup lỗi.
        var startup = new OwnershipRefactorDemo.Trace();
        boolean startupFailed = false;

        try {
            OwnershipRefactorDemo.bootstrap(startup, false, true);
        } catch (IllegalStateException expected) {
            startupFailed = "startup failed".equals(
                expected.getMessage());
        }

        if (!startupFailed) {
            throw new AssertionError(
                "Expected startup failure");
        }
        expect(startup.snapshot(), List.of(
            "client.open", "client.close"));

        // 5. Input sai không được mở session.
        var invalid = new OwnershipRefactorDemo.Trace();

        try (var validApp = OwnershipRefactorDemo
                .bootstrap(invalid, false, false)) {
            try {
                validApp.export(" ");
                throw new AssertionError(
                    "Invalid report ID was accepted");
            } catch (IllegalArgumentException expected) {
                // Dữ liệu sai bị từ chối trước khi mở session.
            }
        }

        expect(invalid.snapshot(), List.of(
            "client.open", "client.close"));

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac OwnershipRefactorDemo.java OwnershipRefactorCheck.java
java OwnershipRefactorCheck
```

Kết quả dự kiến: `PASS`.

Các test tách rõ yêu cầu của một refactor an toàn:

1. **Kết quả và thứ tự side effect** giống nhau ở đường thành công.
2. **Lỗi nghiệp vụ** không bị nuốt và tài nguyên vẫn được đóng.
3. **Một client dài hạn, nhiều session ngắn hạn** vẫn giữ đúng ranh giới.
4. **Startup lỗi sau khi mở client** phải cleanup trước khi ném lỗi.
5. **Input không hợp lệ** không gây I/O thừa.

Lưu ý: Đây là chương trình kiểm thử bằng fake và chuỗi sự kiện, không phải chứng nhận tương đương tuyệt đối của tất cả hành vi. Cần thêm integration test khi client là HTTP, JDBC, SMTP hoặc một SDK có lifecycle riêng.

## 7. Chuyển ownership mà không làm thay đổi API caller

Trong demo, caller cũ sử dụng:

```java
try (LegacyReportExporter exporter = new LegacyReportExporter(...)) {
    exporter.export("R1");
}
```

Sau refactor, caller sử dụng:

```java
try (Application app = bootstrap(...)) {
    app.export("R1");
}
```

Đây là thay đổi **đường API quản lý vòng đời**, dù kết quả nghiệp vụ giữ nguyên. Trong ứng dụng thực tế có nhiều caller, không thể giả định mọi nơi đều cập nhật đồng thời.

Một cách di chuyển theo giai đoạn:

- **Giai đoạn A — giữ façade tương thích:** tạo một wrapper vẫn implement `AutoCloseable`, nhưng wrapper đó **thực sự sở hữu** cả client và service mới. Các caller cũ tiếp tục gọi `close()` trên wrapper.
- **Giai đoạn B — chuyển caller sang root/scope mới:** code startup sở hữu client và truyền service không sở hữu tài nguyên cho những nơi cần dùng.
- **Giai đoạn C — loại bỏ API cũ khi không còn caller:** chỉ khi test và việc tìm call site chứng minh đường cũ đã được thay thế.

Ví dụ façade chuyển tiếp:

```java
// Minh họa độc lập: wrapper là OWNER, service chỉ BORROW.
final class LegacyExporterFacade implements AutoCloseable {
    private final StorageClient ownedClient;
    private final ReportExporter exporter;

    LegacyExporterFacade(StorageSettings settings) {
        this.ownedClient = createClient(settings);
        this.exporter = new ReportExporter(ownedClient);
    }

    String export(String reportId) {
        return exporter.export(reportId);
    }

    @Override
    public void close() {
        ownedClient.close();
    }
}
```

Đây là **pseudocode** vì `StorageSettings` và `createClient(...)` là thành phần của ứng dụng thực, chưa định nghĩa trong file demo. Khi constructor façade có thêm bước có thể thất bại sau `createClient(...)`, phải có `try`/`catch` để cleanup client đã mở.

Façade chỉ là giải pháp quá độ khi cần tương thích. **Không giữ mã cũ và mới cùng là owner của một client**: hai owner độc lập có thể đóng hai lần hoặc đóng sớm.

## 8. Không đồng thời thay đổi scope dùng chung

Một refactor mang tên “đưa client vào DI” thường bị gộp với “đăng ký client thành singleton toàn ứng dụng”. Hai quyết định này độc lập:

```text
Trước:
  Exporter A → Client A
  Exporter B → Client B

Sau, chỉ chuyển ownership (giữ scope):
  Root → Client A → Exporter A
  Root → Client B → Exporter B

Một thay đổi khác, cần đánh giá riêng:
  Root → Client chung → Exporter A
                    └→ Exporter B
```

Gộp hai client thành một có thể thay đổi:

- Số connection hoặc pool được mở.
- State như cookie/session/authentication/cache.
- Tính an toàn luồng khi hai consumer chạy đồng thời.
- Thứ tự shutdown và quyền đóng.
- Giới hạn rate limit, retry budget hoặc throughput.
- Khả năng cô lập lỗi giữa các consumer.

Vì vậy, khi chỉ muốn **di chuyển trách nhiệm tạo/đóng**, hãy giữ **cùng cardinality và lifetime** trước; tối ưu chia sẻ là bước tiếp theo có kiểm thử load và integration riêng.

Ngược lại, nếu client trước đây là một singleton toàn cục nhưng chuyển sang factory tạo mới mỗi request, ứng dụng có thể tăng số connection và thay đổi hiệu năng. DI không yêu cầu transient, singleton hay request scope cố định; scope phải khớp hợp đồng của tài nguyên và hành vi mong muốn.

## 9. Trường hợp nhà cung cấp trả về tài nguyên ngắn hạn

Một use case thường cần hai cấp tài nguyên:

```text
ApplicationRoot
   └── StorageClient dùng chung
         ├── export(R1) → StorageSession #1 → close
         ├── export(R2) → StorageSession #2 → close
         └── shutdown                     → client.close
```

Không nên inject một `StorageSession` sống theo request vào singleton exporter:

```java
// Sai phạm vi nếu một session chỉ hợp lệ cho một request.
final class BadExporter {
    private final StorageSession session;

    BadExporter(StorageSession session) {
        this.session = session;
    }
}
```

Nếu session phải được tạo ở thời điểm gọi, có thể inject `StorageClient` với `openSession()` như ví dụ, hoặc inject một **factory/provider có hợp đồng hẹp**:

```java
@FunctionalInterface
interface StorageSessionFactory {
    StorageSession open();
}

final class SessionBasedExporter {
    private final StorageSessionFactory sessions;

    SessionBasedExporter(StorageSessionFactory sessions) {
        this.sessions = Objects.requireNonNull(sessions);
    }

    void export(String reportId) {
        try (StorageSession session = sessions.open()) {
            session.write(reportId);
        }
    }
}
```

Đây là phác họa thiết kế khi `StorageSession` đã tồn tại và có import `Objects`. Factory không tự bảo đảm session được đóng: caller nhận session phải thực hiện trách nhiệm theo hợp đồng. Nếu `sessions.open()` lỗi **trước khi trả session**, factory phải cleanup phần tài nguyên đã cấp phát nội bộ.

Khi client nằm sau connection pool, `StorageSession.close()` hoặc `Connection.close()` có thể mang nghĩa **trả tài nguyên về pool** thay vì đóng socket vật lý. Không suy luận nghĩa của `close()` chỉ từ tên API; cần xem hợp đồng thư viện.

## 10. Thứ tự đóng theo dependency graph

Khi graph có nhiều tầng:

```text
QueueWorker → ReportExporter → StorageClient → ConnectionPool
```

thứ tự tạo thường từ dependency nền tới consumer:

```text
ConnectionPool → StorageClient → ReportExporter → QueueWorker
```

và thứ tự dừng/đóng thường ngược lại:

```text
QueueWorker → ReportExporter (ngừng dùng client)
            → StorageClient → ConnectionPool
```

**Điều kiện chính:** khi đóng một dependency, không được còn consumer nào đang sử dụng nó. Nếu worker bất đồng bộ vẫn chạy callback, chỉ gọi `worker.close()` nhưng chưa chờ dừng hẳn có thể chưa đủ.

Một quy trình shutdown thực tế thường có các bước:

1. **Ngừng nhận công việc mới** tại listener/queue consumer.
2. **Drain hoặc hủy có kiểm soát** các công việc đang chạy theo deadline.
3. **Kết thúc session/transaction** còn thuộc phạm vi request.
4. **Dừng các consumer nền** đang dùng client/pool.
5. **Đóng tài nguyên dùng chung** theo thứ tự ngược quan hệ phụ thuộc.

Một graph có nhiều nhánh cần chú ý tài nguyên chung được đóng **một lần** sau khi **mọi** consumer đã ngừng sử dụng. Nếu sử dụng DI container, cần kiểm tra thứ tự destroy hook, lazy/scope behavior và cách framework xử lý shutdown lỗi. Container không thể tự biết mọi callback tùy biến của ứng dụng đã hoàn tất.

## 11. Xử lý exception khi giải phóng và startup thất bại

`try-with-resources` bảo đảm gọi `close()` trên resource đã mở thành công khi rời block, kể cả khi phần thân ném exception. Nếu cả phần thân và `close()` đều lỗi, Java giữ exception từ phần thân làm lỗi chính và gắn lỗi đóng dưới dạng **suppressed exception**.

```java
try (AutoCloseable session = () -> {
        throw new IllegalStateException("close failed");
    }) {
    throw new IllegalArgumentException("write failed");
} catch (IllegalArgumentException failure) {
    System.out.println(failure.getMessage()); // write failed
    System.out.println(
        failure.getSuppressed()[0].getMessage()); // close failed
}
```

Trong phần `bootstrap(...)` của demo, nếu khởi động thất bại, client được đóng trước khi ném lại lỗi ban đầu. Nếu cleanup cũng ném `RuntimeException` hoặc `Error`, mã thêm lỗi cleanup vào suppressed. Đây là cách giữ **nguyên nhân khởi động thất bại**, đồng thời không mất tín hiệu sự cố trong cleanup.

Nếu một bước tạo tài nguyên thất bại **trước khi trả instance**, composition root chưa có tài nguyên để đóng. Factory/constructor chịu trách nhiệm dọn phần đã cấp phát dở, ví dụ một socket mở thành công nhưng bước bắt tay TLS thất bại.

Một nguyên tắc hữu ích khi quản lý nhiều tài nguyên là **đăng ký owner ngay sau khi tạo thành công**, rồi giải phóng theo thứ tự ngược. Tuy nhiên, stack LIFO chỉ đúng khi thứ tự tạo tương ứng dependency và quyền sở hữu rõ; với nhiều nhánh chia sẻ hoặc lifecycle bất đồng bộ, có thể cần coordinator đầy đủ hơn.

## 12. Phân biệt refactor hành vi và thay đổi chủ ý về vận hành

Có hai mục tiêu hay bị trộn:

**Mục tiêu A — refactor cấu trúc không đổi hành vi đã cam kết.** Chuyển `new Client` và `client.close()` từ service sang composition root; giữ nguyên thời điểm mở session, kết quả, lỗi, số lần gọi và phạm vi tài nguyên.

**Mục tiêu B — cải thiện vận hành.** Dùng pool chung, thêm retry/timeout, lazy init, health check, đổi shutdown deadline hoặc xử lý lỗi tốt hơn.

B có thể có lợi nhưng có khả năng **thay đổi hành vi**. Ví dụ:

| Thay đổi bổ sung | Hành vi có thể khác |
|---|---|
| Gộp hai client thành một shared client | Concurrency, cache/session state, số kết nối |
| Từ tạo client khi có service sang lazy creation | Thời điểm phát hiện lỗi cấu hình/kết nối |
| Thêm retry | Số lần gọi và side effect; timeout tổng |
| Thêm fallback khi client lỗi | Kết quả nghiệp vụ khi lỗi |
| Đổi request scope thành singleton | Phạm vi state và nguy cơ data leak |
| Đổi thứ tự close | Có thể flush thiếu hoặc làm consumer gặp tài nguyên đã đóng |
| Đổi phương thức `close()` thành no-op | Rò tài nguyên nếu không chuyển owner thực sự |

Nên tách các thay đổi đó thành commit/PR hoặc bước triển khai riêng, có kiểm thử và kế hoạch rollback. Đổi ownership mà đồng thời đổi pooling có thể làm khó xác định lỗi đến từ đâu khi sản phẩm xảy ra sự cố.

## 13. Nếu chuyển sang DI container thì sao?

Trong Java thuần, composition root quản lý client như `bootstrap(...)` đã minh họa. Khi chuyển sang DI container, có thể để container tạo và quản lý một client application-scoped, inject nó cho nhiều service và gọi destroy hook lúc application context đóng.

Tuy nhiên, các câu hỏi vẫn không thay đổi:

- **Container có thật sự sở hữu instance đó không?** Một instance được tạo ở bên ngoài rồi đăng ký vào container có thể có quy tắc disposal khác với instance container tự tạo.
- **Scope là gì?** Singleton thường có nghĩa một instance trong một application context/registration, không phải toàn JVM.
- **Ai đóng tài nguyên transient?** Không được giả định container nào cũng theo dõi mọi instance `AutoCloseable` giống nhau.
- **Consumer có còn giữ tham chiếu sau khi scope đóng không?** Cần tránh captive dependency.
- **Thứ tự shutdown?** Container có biết các consumer bất đồng bộ phải drain trước khi đóng client không?
- **Khi khởi tạo một phần graph bị lỗi?** Các bean/resource đã tạo được cleanup thế nào?

Tránh inject toàn bộ container vào `ReportExporter` rồi gọi `getBean(StorageClient.class)` trong mỗi method. Đó là kiểu **Service Locator**, làm phụ thuộc khó quan sát. Consumer nên giữ constructor injection tường minh; container chỉ đảm nhiệm phần composition và lifecycle đã được cấu hình.

**Quan trọng:** annotation như `@PreDestroy` hay interface destroy của một framework có thể hỗ trợ đóng, nhưng cơ chế và thứ tự cụ thể tùy framework/version. Chỉ chuyển owner sang container khi đã xác nhận hợp đồng đóng và đã kiểm thử shutdown.

## 14. Danh sách kiểm tra trước khi chấp nhận refactor

Có thể dùng bảng sau trong code review hoặc mô tả PR:

| Hạng mục | Câu hỏi xác nhận |
|---|---|
| **Đường cấp phụ thuộc** | Service đã nhận client qua constructor thay vì tự tạo? |
| **Một owner rõ ràng** | Client có đúng một nơi chịu trách nhiệm đóng cuối cùng? |
| **Không double-close** | Consumer không tự đóng shared client được inject? |
| **Không leak** | Owner đóng client ở thành công, lỗi startup và shutdown? |
| **Đúng scope** | Client vẫn sống lâu như trước; session vẫn sống đúng một lời gọi? |
| **Đúng thứ tự** | Worker/listener dừng trước khi tài nguyên nền bị đóng? |
| **Đường thành công** | Kết quả và side effect không thay đổi ngoài kế hoạch? |
| **Đường lỗi** | Exception và cleanup vẫn được quan sát đúng? |
| **Input sai** | Có bị từ chối trước I/O như trước không? |
| **Tương thích API** | Caller của `close()` cũ đã được di chuyển hoặc giữ façade? |
| **Concurrency** | Có vô tình chia sẻ client vốn không thread-safe không? |
| **Giám sát** | Có đủ log/metrics để phát hiện rò tài nguyên, shutdown lỗi? |
| **Rollback** | Có thể quay lại wiring cũ nếu triển khai gặp sự cố? |

Không phải mọi mục đều cần một test riêng, nhưng từng mục quan trọng phải có bằng chứng: unit/characterization test, integration test, quan sát lifecycle hoặc phân tích hợp đồng của thư viện.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Chỉ đổi `new` thành tham số constructor, giữ nguyên `client.close()` trong service | Consumer đóng nhầm dependency dùng chung | Tách owner khỏi consumer |
| Bỏ `close()` của service nhưng không có owner mới | Rò pool, thread, socket | Composition root hoặc scope có trách nhiệm close |
| Gộp nhiều client thành singleton trong cùng refactor | Thay đổi state/concurrency không được kiểm thử | Giữ lifetime trước, tối ưu chia sẻ sau |
| Đưa session ngắn hạn vào constructor singleton | Dùng session qua nhiều request hoặc sau khi đã đóng | Inject client/factory và mở session trong thao tác |
| Đóng pool ngay khi một request kết thúc | Các request khác đang dùng pool bị lỗi | Root/container sở hữu shared pool |
| Mất cleanup khi một bước bootstrap lỗi | Rò tài nguyên đã tạo thành công | `try`/`catch` và đóng theo owner |
| Gọi `close()` trên factory result khi chưa tạo thành công | Có thể không có instance hợp lệ | Factory dọn cấp phát dở của chính nó |
| Test chỉ so sánh giá trị trả về | Bỏ qua leak, double-close, sai thứ tự side effect | Ghi trace mở/dùng/đóng ở cả đường lỗi |
| Trộn thay đổi retry, timeout và pooling với chuyển owner | Khó chứng minh hành vi không đổi | Tách thành bước triển khai độc lập |
| Nghĩ DI container tự bảo đảm shutdown hoàn chỉnh | Callback/worker còn chạy sau khi bean đã đóng | Thiết kế stop/drain/dispose rõ ràng |

## 16. Bài tập thực hành

**Bài tập 1 — Xác định owner hiện hành.** Một service tự tạo `HttpClient` ở constructor, mỗi method tạo một request object. Nó implement `AutoCloseable` để đóng client. Hãy vẽ graph ownership hiện tại và đề xuất vị trí tạo/đóng client sau refactor, chưa thay đổi số instance hoặc scope.

**Bài tập 2 — Giữ thứ tự tài nguyên.** Từ `OwnershipRefactorDemo`, gọi hai lần `export(...)` trước khi đóng app. Viết danh sách sự kiện dự kiến. Vì sao chỉ có một `client.open` và một `client.close` nhưng có hai cặp `session.open` / `session.close`?

**Bài tập 3 — Kiểm tra đường lỗi.** Cho `TracedStorageClient` ném `IllegalStateException("write failed")` trong `write(...)`. Xác minh `session.close` và `client.close` vẫn xảy ra; lỗi gốc phải tới caller, không bị chuyển thành kết quả `EXPORTED ...`.

**Bài tập 4 — Chuyển caller cũ.** Một module dùng `try (LegacyReportExporter e = ...)`. Thiết kế façade tương thích `AutoCloseable` để tiếp tục cung cấp API `export(...)` và `close()`, nhưng bên trong delegating cho `ReportExporter` không sở hữu client. Ai là owner trong giai đoạn chuyển tiếp?

**Bài tập 5 — Bắt lỗi khởi động.** Thêm một bước tạo `MetricsCollector` sau `StorageClient` trong `bootstrap(...)`, rồi mô phỏng bước đó thất bại. Hãy bảo đảm client đã tạo được đóng. Nếu `MetricsCollector` tạo dở một thread trước khi ném lỗi, ai chịu trách nhiệm dọn thread chưa bàn giao?

**Bài tập 6 — Phân biệt refactor và tối ưu.** Sau khi chuyển owner thành công, muốn dùng chung một client cho hai exporter. Hãy lập danh sách test mới cần có: thread safety, request isolation, shutdown ordering, số kết nối, lỗi khi một exporter ngừng dùng và exporter còn lại tiếp tục.

**Bài tập 7 — Kiểm chứng với DI container.** Khi chuyển client sang singleton bean, xác định bean được container tự tạo hay do caller cấp. Đọc hợp đồng destroy tương ứng; viết integration test đóng context sau khi dừng worker và xác minh tài nguyên thực được đóng đúng một lần.

### Câu hỏi tự kiểm tra

1. Nhận một client qua constructor có đồng nghĩa service sở hữu client đó không?
2. Vì sao kết quả nghiệp vụ đúng vẫn chưa đủ chứng minh refactor giữ nguyên hành vi?
3. Nếu trước kia mỗi service có client riêng, đổi sang một singleton chung có phải refactor thuần túy không?
4. Khi `export(...)` mở session từ client được inject, ai đóng session và ai đóng client?
5. Nếu client được tạo xong nhưng bước lắp graph tiếp theo thất bại, ai chịu trách nhiệm cleanup?
6. Nếu factory thất bại trước khi trả tài nguyên, vì sao composition root không thể tự đóng instance chưa nhận được?
7. Vì sao phải dừng worker trước khi đóng pool đang được worker sử dụng?
8. Khi caller cũ phụ thuộc vào `close()`, có thể dùng façade tương thích như thế nào?
9. Nếu một close thất bại trong lúc xử lý lỗi ban đầu, tại sao cần suppressed exceptions?
10. DI container có thay thế hoàn toàn việc xác định ownership không?

**Gợi ý:** (1) Không; (2) còn side effect, scope, thứ tự và cleanup; (3) không, có thay đổi concurrency/lifetime; (4) caller/scope của session và owner của client; (5) composition root; (6) factory phải dọn phần mở dở; (7) tránh dùng dependency đã đóng; (8) wrapper thực sự sở hữu client mới và delegate cho service; (9) giữ lỗi gốc mà không mất thông tin cleanup; (10) không.

## Ghi nhớ

- **Chuyển sang DI không chỉ là thay `new` bằng constructor parameter.** Phải chuyển rõ quyền tạo và đóng tài nguyên tới owner phù hợp.
- **Consumer không mặc nhiên là owner:** service dùng client được inject không tự ý đóng client chung; session mở theo từng lời gọi vẫn cần đóng đúng scope.
- **Bảo toàn hành vi bằng bằng chứng:** so sánh kết quả, lỗi, số lần mở/ghi/đóng, thứ tự sự kiện và xử lý khi startup thất bại.
- **Không trộn đổi scope với chuyển ownership:** giữ nguyên lifetime/cardinality trước, rồi tối ưu dùng chung hoặc pooling bằng bước riêng.
- **Đóng theo quan hệ phụ thuộc:** ngừng consumer và drain công việc trước khi đóng tài nguyên nền; xử lý lỗi cleanup và suppressed exceptions.
- **Composition root hay DI container đều phải có hợp đồng sở hữu rõ**, kể cả khi container tự quản lý bean. Constructor injection giữ business service dễ kiểm thử bằng Java thuần.
