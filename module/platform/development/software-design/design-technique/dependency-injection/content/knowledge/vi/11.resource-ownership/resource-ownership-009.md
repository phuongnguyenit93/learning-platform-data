# Rò rỉ tài nguyên khi factory hoặc provider tạo instance ngoài quản lý

Trong **Dependency Injection (DI)**, một lớp có thể nhận trực tiếp cộng tác viên qua constructor, hoặc nhận một **factory/provider** để tạo cộng tác viên khi cần. Cách thứ hai hữu ích khi mỗi thao tác cần một kết nối, session, stream hoặc đối tượng mang trạng thái riêng. Tuy nhiên, nó dễ phát sinh lỗi nếu người viết chỉ quan tâm đến **ai tạo instance** mà bỏ qua **ai có trách nhiệm đóng instance ấy**.

Giả sử một service được tiêm `SessionFactory`, rồi gọi `factory.open()` cho mỗi lần lưu tài liệu. Factory đã được lắp ghép đúng theo DI, nhưng kết quả của `open()` có thể là **resource mới ngoài phạm vi quản lý tự động của container**. Nếu mỗi session cần `close()` mà consumer bỏ qua, hệ thống có thể cạn connection pool, giữ socket hoặc file handle quá lâu, ngay cả khi từng thao tác nghiệp vụ nhìn có vẻ thành công.

Bài thuộc chương **Sở hữu tài nguyên** của module **Dependency Injection**. Mục tiêu là xác định ranh giới ownership khi sử dụng factory/provider, thực hành `try-with-resources` bằng Java 17 thuần, hiểu vòng đời ở composition root và phân tích các đường lỗi trước khi chuyển sang DI container.

## 1. Lắp ghép đúng phụ thuộc vẫn có thể rò rỉ tài nguyên

Xét service sau, với hai interface sẽ được định nghĩa đầy đủ ở phần thực hành:

~~~java
final class DocumentService {
    private final SessionFactory factory;

    DocumentService(SessionFactory factory) {
        this.factory = java.util.Objects.requireNonNull(factory);
    }

    void store(String content) {
        StorageSession session = factory.open();
        session.save(content);
        // Bỏ quên session.close().
    }
}
~~~

`DocumentService` không tự chọn loại session và cũng không tự tạo một adapter cụ thể. Đây là **constructor injection hợp lệ**. Nhưng mỗi lần gọi `store()` có thể tạo một session mới mà không bao giờ giải phóng.

Hệ quả phụ thuộc loại tài nguyên:

| Tài nguyên do factory cấp | Nếu không hoàn tất cleanup | Dấu hiệu |
| --- | --- | --- |
| Connection/session mượn từ pool | Connection không được trả về pool đúng lúc | Pool cạn, request chờ hoặc timeout |
| File hoặc network stream | File descriptor/socket tiếp tục bị giữ | Số handle tăng; lỗi mở tài nguyên mới |
| Buffer trực tiếp/handle native | Tài nguyên ngoài heap được giữ lâu hơn nhu cầu | Áp lực bộ nhớ và native resource |
| Subscription/listener | Callback vẫn đăng ký sau khi tác vụ kết thúc | Tích lũy listener, xử lý lặp, giữ tham chiếu |
| Temporary file | File không được xóa theo chính sách | Dung lượng lưu trữ tăng |

**Rò rỉ tài nguyên không nhất thiết là rò rỉ heap.** Một object không còn tham chiếu Java vẫn có thể từng sở hữu handle cần giải phóng theo giao thức riêng. Garbage collector không phải công cụ thay thế cho một lịch đóng tài nguyên xác định; nhiều pool chỉ trả connection về khi caller gọi `close()`.

Ngược lại, không phải mọi sản phẩm của factory đều phải đóng. Nếu factory chỉ tạo record bất biến hoặc một đối tượng tính toán không giữ tài nguyên, việc dùng `AutoCloseable` có thể không cần thiết. Hãy phân tích **hợp đồng thực tế của sản phẩm**, thay vì áp dụng máy móc.

## 2. Ai tạo, ai dùng, ai sở hữu?

Ba vai trò cần được tách bạch:

1. **Creator:** nơi gọi constructor/factory để tạo một đối tượng.
2. **Consumer:** nơi sử dụng phương thức của đối tượng đó.
3. **Owner:** nơi chịu trách nhiệm bảo đảm đối tượng được kết thúc vòng đời đúng thời điểm, kể cả khi có ngoại lệ.

Một đối tượng có thể **được cung cấp từ ngoài nhưng consumer được chuyển quyền sở hữu**; cũng có thể consumer chỉ **mượn** đối tượng mà composition root đang sở hữu.

| Trường hợp | Bên thường chịu trách nhiệm đóng | Vì sao |
| --- | --- | --- |
| Consumer gọi `factory.open()`, hợp đồng trả một session mới **caller-owned** | Consumer, sau mỗi thao tác | Caller nhận resource mới và phải hoàn trả |
| Composition root tạo một connection pool rồi inject cho nhiều service | Composition root/lifecycle manager | Pool được dùng chung suốt vòng đời ứng dụng |
| Caller mở `OutputStream` rồi truyền cho một phương thức ghi | Caller, nếu không có chuyển giao ownership | Phương thức chỉ mượn stream |
| Factory xây dựng facade sở hữu client nội bộ | Facade hoặc component nhận chuyển giao ownership | Vòng đời client gắn với facade |
| Provider lấy một bean đang nằm trong scope do container quản lý | Tùy lifecycle contract của framework | Container có thể chịu trách nhiệm theo đăng ký cụ thể |

**Quy tắc quan trọng:** không suy trách nhiệm đóng từ vị trí đặt lệnh `new`, tên `Provider` hoặc sự hiện diện của annotation DI. Cần một **hợp đồng ownership tường minh**.

Trong một codebase lớn, nên ghi ngay trong JavaDoc hoặc API: phương thức trả về **instance mới thuộc caller**, **tham chiếu mượn không được đóng**, hay **đối tượng được container quản lý**. Nếu caller phải suy đoán, rất dễ xuất hiện cả lỗi rò rỉ lẫn lỗi đóng nhầm.

## 3. Vì sao quản lý factory không đồng nghĩa quản lý sản phẩm?

Một API tối giản:

~~~java
interface StorageSession extends AutoCloseable {
    void save(String content);

    @Override
    void close();
}

@FunctionalInterface
interface SessionFactory {
    // Ví dụ hợp đồng: mỗi lần mở là một session mới, caller sở hữu.
    StorageSession open();
}
~~~

Composition root có thể tạo một `SessionFactory` dùng chung rồi tiêm vào nhiều service. Nhưng từng `StorageSession` do `open()` tạo có **vòng đời riêng**. Nếu session nằm ngoài hệ thống đăng ký/khởi tạo của DI container, container có thể không biết nó tồn tại.

~~~mermaid
flowchart TD
    Root["Composition root / DI container"] -->|"tạo, tiêm"| Factory["SessionFactory dùng chung"]
    Root -->|"tiêm factory"| Service["DocumentService"]
    Service -->|"open lần 1"| A["StorageSession A"]
    Service -->|"open lần 2"| B["StorageSession B"]
    Service -->|"đóng khi hoàn tất A"| A
    Service -->|"đóng khi hoàn tất B"| B
~~~

Đây là điểm khác nhau giữa **vòng đời factory** và **vòng đời sản phẩm**:

- Factory có thể sống suốt ứng dụng vì giữ cấu hình hoặc connection pool.
- Session có thể chỉ sống trong một thao tác, request hoặc transaction.
- Service được tiêm factory không vì thế trở thành owner của **pool dùng chung**, dù nó có thể sở hữu **session mới vừa nhận**.

Với `Supplier<T>`, `Provider<T>` và `Factory<T>` cũng vậy. Một provider có thể tạo mới, dùng cache, trả về bean theo request scope hoặc cung cấp object container đã quản lý. **Tên API không xác định chính sách này**. Một số container tự quản lý sản phẩm được tạo qua registration của chính nó; một số cơ chế prototype/transient lại yêu cầu consumer tự thực hiện cleanup. Phải kiểm tra semantics của framework và từng binding, không đưa ra kết luận chung cho mọi container.

## 4. Đóng resource caller-owned bằng try-with-resources

Khi hợp đồng của `SessionFactory.open()` nói rõ caller sở hữu session mới và session triển khai `AutoCloseable`, cách viết đơn giản là:

~~~java
final class DocumentService {
    private final SessionFactory factory;

    DocumentService(SessionFactory factory) {
        this.factory = java.util.Objects.requireNonNull(factory, "factory");
    }

    void store(String content) {
        try (StorageSession session =
                     java.util.Objects.requireNonNull(
                             factory.open(), "opened session")) {
            session.save(content);
        }
    }
}
~~~

`try-with-resources` tự gọi `close()` khi kết thúc khối, kể cả nếu `save()` ném ngoại lệ. Lúc này **service sở hữu session trong phạm vi một lời gọi**, nhưng **không sở hữu factory** nên không được tùy tiện đóng factory sau lời gọi.

Có ba đường lỗi cần phân biệt:

- **`open()` thành công, `save()` thất bại:** `close()` vẫn được gọi.
- **`open()` thất bại trước khi trả object:** consumer chưa nhận được session nên không thể đóng thứ chưa được trả. **Factory** phải cleanup những resource nó đã tạo một phần.
- **`close()` cũng thất bại:** nếu thân `try` đã ném ngoại lệ khác, Java giữ ngoại lệ chính và bổ sung ngoại lệ cleanup vào danh sách **suppressed exceptions**. Nếu thân `try` thành công nhưng `close()` lỗi, lỗi đóng sẽ được truyền ra theo quy tắc Java.

Không nên dùng `try-with-resources` cho một object **đang được mượn** nếu API không cho phép caller đóng nó. Với resource được caller mở sẵn rồi truyền vào, trách nhiệm đóng thường thuộc caller trừ khi hợp đồng đã chuyển giao.

## 5. Ví dụ Java 17 chạy độc lập: mỗi lần tạo phải đóng đúng một lần

Ví dụ sau kiểm tra rằng service mở session cho mỗi lần lưu, và đóng **từng instance** khi thành công hoặc thất bại. Toàn bộ ví dụ dùng Java thuần, không cần database thật hay thư viện mock.

Lưu mã vào tệp `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

interface StorageSession extends AutoCloseable {
    void save(String content);

    @Override
    void close();
}

@FunctionalInterface
interface SessionFactory {
    // Mỗi lần open tạo session mới, caller chịu trách nhiệm close.
    StorageSession open();
}

final class DocumentService {
    private final SessionFactory sessions;

    DocumentService(SessionFactory sessions) {
        this.sessions = Objects.requireNonNull(sessions, "sessions");
    }

    void store(String content) {
        Objects.requireNonNull(content, "content");
        try (StorageSession session =
                     Objects.requireNonNull(sessions.open(), "session")) {
            session.save(content);
        }
    }
}

final class TrackingSession implements StorageSession {
    private final boolean failOnSave;
    private final List<String> saved = new ArrayList<>();
    private boolean closed;
    private int closeCalls;

    TrackingSession(boolean failOnSave) {
        this.failOnSave = failOnSave;
    }

    @Override
    public void save(String content) {
        if (closed) {
            throw new IllegalStateException("Session already closed");
        }
        if (failOnSave) {
            throw new IllegalStateException("Simulated storage failure");
        }
        saved.add(content);
    }

    @Override
    public void close() {
        if (closed) {
            throw new IllegalStateException("Session closed twice");
        }
        closed = true;
        closeCalls++;
    }

    boolean isClosed() {
        return closed;
    }

    int closeCalls() {
        return closeCalls;
    }

    List<String> saved() {
        return List.copyOf(saved);
    }
}

final class TrackingSessionFactory implements SessionFactory {
    private final boolean failOnSave;
    private final List<TrackingSession> opened = new ArrayList<>();

    TrackingSessionFactory(boolean failOnSave) {
        this.failOnSave = failOnSave;
    }

    @Override
    public StorageSession open() {
        TrackingSession session = new TrackingSession(failOnSave);
        opened.add(session);
        return session;
    }

    List<TrackingSession> opened() {
        return List.copyOf(opened);
    }
}

public class Main {
    public static void main(String[] args) {
        // Composition root tạo factory và tiêm qua constructor.
        TrackingSessionFactory successFactory =
                new TrackingSessionFactory(false);
        DocumentService service = new DocumentService(successFactory);

        service.store("A");
        service.store("B");

        List<TrackingSession> successSessions = successFactory.opened();
        check(successSessions.size() == 2,
                "Mỗi thao tác phải mở một session");
        check(successSessions.get(0) != successSessions.get(1),
                "Hai session phải là hai instance riêng");
        check(successSessions.get(0).saved().equals(List.of("A")),
                "Session đầu phải ghi A");
        check(successSessions.get(1).saved().equals(List.of("B")),
                "Session thứ hai phải ghi B");
        for (TrackingSession session : successSessions) {
            check(session.isClosed() && session.closeCalls() == 1,
                    "Session thành công phải đóng đúng một lần");
        }

        // Đường lỗi: save ném ngoại lệ, try vẫn đóng session.
        TrackingSessionFactory failureFactory =
                new TrackingSessionFactory(true);
        DocumentService failingService = new DocumentService(failureFactory);

        boolean failed = false;
        try {
            failingService.store("C");
        } catch (IllegalStateException expected) {
            failed = true;
        }
        check(failed, "Phải quan sát được lỗi save");

        List<TrackingSession> failureSessions = failureFactory.opened();
        check(failureSessions.size() == 1,
                "Đường lỗi phải tạo đúng một session");
        check(failureSessions.get(0).isClosed()
                        && failureSessions.get(0).closeCalls() == 1,
                "Session lỗi vẫn phải đóng đúng một lần");

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

Ví dụ minh họa **một factory dùng chung** vẫn có thể cấp **hai session riêng**, và từng session cần được đóng theo vòng đời của thao tác. Test kiểm tra rõ **số instance đã tạo, số lần đóng, dữ liệu đã ghi và cleanup trên đường lỗi**.

**Giới hạn của test double:** `TrackingSessionFactory` giữ danh sách session để test quan sát. Đó là cơ chế kiểm thử; trong production, factory không nên vô hạn giữ mọi session đã tạo vì chính collection đó có thể giữ tham chiếu và gây tăng bộ nhớ không cần thiết.

## 6. Factory có resource dùng chung: hai cấp quyền sở hữu

Một factory thật có thể giữ connection pool hoặc một client dùng chung. Khi đó có hai vòng đời cần phân biệt:

| Thành phần | Phạm vi điển hình | Owner |
| --- | --- | --- |
| Pool/factory dùng chung | Vòng đời ứng dụng/context | Composition root hoặc lifecycle manager |
| Connection/session mượn từ pool | Transaction/request/tác vụ | Caller hoặc transaction manager theo hợp đồng |
| Stream do caller đưa vào một API | Phạm vi caller | Caller, trừ khi chuyển giao ownership |
| Factory tạo một facade gồm nhiều tài nguyên nội bộ | Vòng đời facade | Facade hoặc owner được chỉ định |
| Instance do container quản lý trực tiếp | Theo scope/binding | Theo lifecycle contract của container |

~~~mermaid
flowchart TD
    Root["Composition root"] -->|"tạo và sở hữu"| Factory["Factory / pool dùng chung"]
    Root --> ServiceA["Service A"]
    Root --> ServiceB["Service B"]
    ServiceA -->|"dùng factory"| Factory
    ServiceB -->|"dùng factory"| Factory
    Factory -->|"cấp"| SessionA["Session A"]
    Factory -->|"cấp"| SessionB["Session B"]
    ServiceA -->|"close khi xong A"| SessionA
    ServiceB -->|"close khi xong B"| SessionB
    Root -->|"đóng pool lúc ứng dụng kết thúc"| Factory
~~~

Nếu service đóng **pool** sau một request thì service khác có thể bị ngắt. Nếu root chỉ đóng pool khi ứng dụng tắt, nhưng các **session** không được trả về sau từng request, pool vẫn có thể cạn từ rất sớm. Cần cả hai mức cleanup.

Khi một class bình thường nhận qua constructor một factory có `close()`, cũng không vì thế mà class ấy đương nhiên được phép gọi `factory.close()`. Việc **được tiêm** một tham chiếu thể hiện quyền sử dụng theo hợp đồng; quyền sở hữu tài nguyên cần được xác định riêng.

## 7. Factory khởi tạo dở dang: cleanup trước khi chuyển giao

`try-with-resources` ở consumer chỉ thấy các resource **được trả về thành công**. Nếu factory mở file, sau đó khởi tạo codec bị lỗi, consumer chưa nhận được file handle và không thể dọn thay factory.

Một factory cần tuân nguyên tắc:

1. Khi đang tạo, **factory sở hữu** các tài nguyên tạm đã mở.
2. Nếu bước tiếp theo thất bại, factory phải **cleanup** tài nguyên đã tạo.
3. Khi object hoàn chỉnh được trả về và hợp đồng chuyển ownership, **caller/aggregate nhận quyền sở hữu** và chịu trách nhiệm đóng về sau.

Ví dụ cấu trúc (các kiểu `Resource`, `Client`, `openResource` và `configureClient` là giả định):

~~~java
Resource resource = openResource();
try {
    Client client = configureClient(resource);
    // configure thành công: client nhận ownership của resource.
    return client;
} catch (RuntimeException | Error original) {
    try {
        resource.close();
    } catch (Exception cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
    throw original;
}
~~~

Đây là đoạn minh họa trong một factory method, không phải tệp Java biên dịch độc lập. Nó giả định **Client** được tạo thành công sẽ đóng `resource` sau này. Nếu dùng `try-with-resources` bao quanh `return client` mà không có cơ chế chuyển giao, resource sẽ bị đóng **ngay lúc factory trả về**, trước khi caller sử dụng.

Trong thực tế, code xây dựng nhiều tài nguyên có thể cần cơ chế cleanup theo thứ tự ngược và giữ nguyên nguyên nhân lỗi. Khi việc đóng có thể ném lỗi, sử dụng suppressed exceptions hoặc cơ chế tương đương để không vô tình che mất ngoại lệ khởi tạo chính.

## 8. New instance, cached instance và borrowed instance không tương đương

Hai implementation có thể dùng cùng interface `Supplier<StorageSession>` nhưng mang ngữ nghĩa ownership khác nhau:

~~~java
// Minh họa, openNewSession() là phương thức giả định.
java.util.function.Supplier<StorageSession> perCall =
        () -> openNewSession(); // Mỗi lần gọi tạo mới.

// sharedSession đã được tạo và thuộc owner khác.
java.util.function.Supplier<StorageSession> shared =
        () -> sharedSession; // Luôn trả cùng một reference.
~~~

Với `perCall`, nếu mỗi lần trả session mới thuộc caller thì caller phải đóng **mỗi instance**. Với `shared`, nếu session được **mượn** thì đóng sau từng lời gọi sẽ phá vỡ các consumer khác. Vì vậy, **chỉ nhìn kiểu `Supplier<T>` không đủ để quyết định có nên dùng try-with-resources hay không**.

Nên làm hợp đồng đủ rõ bằng tên hoặc tài liệu như `openOwnedSession()`, `borrowSession()`, `withSession(action)` và các quy tắc đóng tương ứng. Với API mượn/trả, đặc biệt là connection pool, thao tác `close()` trên wrapper có thể mang nghĩa **trả về pool** chứ không đóng socket vật lý. Đây vẫn là một cleanup bắt buộc ở scope của caller.

Một API chọn cách sở hữu hoàn toàn vòng đời trong callback:

~~~java
interface SessionRunner {
    void withSession(java.util.function.Consumer<StorageSession> action);
}

final class DefaultSessionRunner implements SessionRunner {
    private final SessionFactory factory;

    DefaultSessionRunner(SessionFactory factory) {
        this.factory = java.util.Objects.requireNonNull(factory);
    }

    @Override
    public void withSession(java.util.function.Consumer<StorageSession> action) {
        java.util.Objects.requireNonNull(action, "action");
        try (StorageSession session = factory.open()) {
            action.accept(session);
        }
    }
}
~~~

Trong ví dụ này, `withSession` **tự đóng session sau khi callback đồng bộ hoàn tất**. Caller không được giữ tham chiếu session để dùng sau khi callback kết thúc. Nếu muốn công việc bất đồng bộ, hợp đồng cần được thiết kế khác.

## 9. Bất đồng bộ: đóng quá sớm cũng là lỗi vòng đời

Đoạn sau có vấn đề dù đã có `try-with-resources`:

~~~java
// Minh họa một phương thức có trường factory.
java.util.concurrent.CompletableFuture<Void> submit(String content) {
    try (StorageSession session = factory.open()) {
        return java.util.concurrent.CompletableFuture.runAsync(
                () -> session.save(content));
    }
}
~~~

Khối `try` kết thúc ngay sau khi lên lịch tác vụ, trong khi công việc bất đồng bộ có thể **chưa bắt đầu**. Session bị đóng quá sớm.

Nếu mỗi tác vụ tự sở hữu session, hãy **mở và đóng trong chính tác vụ**:

~~~java
java.util.concurrent.CompletableFuture<Void> submit(
        String content, java.util.concurrent.Executor executor) {
    return java.util.concurrent.CompletableFuture.runAsync(() -> {
        try (StorageSession session = factory.open()) {
            session.save(content);
        }
    }, executor);
}
~~~

Các đoạn trên chỉ minh họa cách tổ chức phương thức, chưa phải lớp chạy độc lập. Chúng giả định `factory` có sẵn trong lớp, và `executor` là dependency do bên ngoài quản lý; phương thức không tự `shutdown()` executor dùng chung.

Nếu workflow có nhiều bước async, resource có thể cần sống đến khi mọi bước hoàn thành hoặc bị hủy. Phải xác định owner của **toàn bộ pipeline**, xử lý timeout/cancel và tránh vừa rò rỉ vừa đóng trước khi consumer cuối cùng hoàn tất.

## 10. Phát hiện rò rỉ và kiểm chứng hợp đồng ownership

Một số tín hiệu đáng kiểm tra:

| Dấu hiệu | Điều cần điều tra |
| --- | --- |
| Connection pool còn rất ít phần tử khả dụng dù tải đã giảm | Session/connection chưa được trả hoặc giữ quá lâu |
| Số file descriptor/socket tăng dần | Stream/response/client không được đóng đúng scope |
| Request chờ pool ngày càng lâu | Rò rỉ hoặc transaction giữ tài nguyên vượt thời gian dự kiến |
| Số object/callback được giữ tăng dù tác vụ đã kết thúc | Cache hoặc registry trong provider giữ tham chiếu |
| Chạy test song song mới lỗi | Đóng nhầm tài nguyên chung, dùng sai scope hoặc tranh chấp state |

Cách kiểm tra hiệu quả gồm việc **vẽ đường đi ownership** từ tạo → chuyển giao → sử dụng → cleanup, đo số lượng resource đang active, và mô phỏng lỗi đúng tại các điểm dễ bị bỏ sót như mở resource, ghi dữ liệu, đóng resource hoặc hủy async.

Với bài kiểm thử, nên xác minh cả hai khía cạnh: hành vi nghiệp vụ và **đúng một cleanup khi owner kết thúc sử dụng**. Test lắp ghép cũng cần kiểm tra rằng pool/client dùng chung được đóng tại application root và không bị từng consumer đóng sớm.

Một cảnh báo “connection leak” từ công cụ giám sát chưa đủ chứng minh có rò rỉ vĩnh viễn: đôi khi transaction hợp lệ giữ connection quá lâu. Cần phân biệt **rò rỉ**, **giữ resource lâu bất thường** và **đóng quá sớm**.

## 11. Những lỗi thiết kế thường gặp

### 11.1. Cho rằng provider được inject nên container tự cleanup mọi product

~~~java
StorageSession session = factory.open();
session.save(content);
// Factory đã được inject; không có nghĩa session được tự đóng.
~~~

Container có thể quản lý factory nhưng không biết từng instance do một factory thủ công tạo ngoài registration. Cần đọc lifecycle contract thực tế.

### 11.2. Đóng pool trong từng consumer

Một service có thể cần trả session về pool nhưng không có quyền đóng **pool dùng chung**. Quyền đóng pool thuộc owner toàn ứng dụng hoặc lifecycle manager theo thỏa thuận.

### 11.3. Đóng resource chỉ ở cuối đường thành công

~~~java
StorageSession session = factory.open();
session.save(content); // Nếu lỗi, dòng bên dưới không chạy.
session.close();
~~~

Dùng `try-with-resources` cho resource caller-owned trong thao tác đồng bộ.

### 11.4. Tạo resource rồi ném lỗi trước khi trả mà không dọn

Nếu factory đã mở handle mà bước cấu hình sau đó thất bại, factory còn là owner và phải thu hồi ngay; consumer chưa thể đóng.

### 11.5. Cache mọi sản phẩm của provider để “dễ quản lý”

Collection giữ mọi session/response có thể giữ cả heap lẫn resource ngoài heap vô thời hạn. Cache cần có chính sách eviction, giới hạn, scope và cleanup phù hợp.

### 11.6. Dùng chung transaction/session cho mọi request

Vòng đời một session có trạng thái theo request khác với pool hoặc factory dùng chung. DI nên cho phép chia sẻ **factory/pool**, còn cấp instance ngắn hạn theo request/transaction khi phù hợp.

## 12. Bài tập thực hành

**Bài 1 — Sửa đường rò rỉ.** Một `ExportService` nhận `Supplier<OutputStream>`, gọi `get()` để lấy stream mới rồi ghi dữ liệu nhưng không đóng. Hãy thêm cleanup cho hợp đồng stream **caller-owned**. Sau đó giải thích tại sao cách đó sai nếu supplier chỉ trả một stream **borrowed**.

**Bài 2 — Kiểm thử lỗi.** Sửa test double ở mục 5 để lần lưu thứ hai thất bại. Xác minh rằng cả session của lần thành công và session của lần thất bại đều đóng đúng một lần.

**Bài 3 — Hai cấp ownership.** Composition root tạo pool dùng chung, factory mượn connection từ pool cho từng transaction. Ai đóng pool? Ai trả connection? Điều gì xảy ra nếu consumer đóng pool sau request đầu tiên?

**Bài 4 — Lỗi khi tạo.** Factory mở một file rồi tạo encoder nhưng encoder ném lỗi. Hãy thiết kế cleanup trước khi trả; khi trả về một object hoàn chỉnh thì ownership cần chuyển cho ai?

**Bài 5 — Async.** Giải thích vì sao mở resource ngoài callback rồi trả `CompletableFuture` có thể đóng quá sớm. Đề xuất thời điểm mở/đóng đúng khi task hoàn tất, thất bại hoặc bị hủy.

## 13. Tự kiểm tra mức độ hiểu

**Câu 1.** Inject một singleton factory có làm mọi session do factory trả về thành singleton không? **Không.** Scope factory và scope product là hai hợp đồng riêng.

**Câu 2.** Nếu `save()` ném ngoại lệ trong `try-with-resources`, `close()` có được gọi không? **Có**, nếu session đã được khởi tạo thành công cho khối `try`.

**Câu 3.** Factory mở socket rồi lỗi trước khi trả session. Ai phải đóng socket? **Factory**, vì chưa chuyển giao ownership cho caller.

**Câu 4.** Nếu một stream được caller mở sẵn rồi tiêm vào service, service có được tự đóng không? **Chỉ khi hợp đồng chuyển ownership**. Nếu service chỉ mượn, caller còn trách nhiệm đóng.

**Câu 5.** Provider được DI container cấp có bảo đảm container sẽ đóng mọi object trả về không? **Không thể kết luận chung.** Phải xem cách container đăng ký/tạo sản phẩm, scope và lifecycle contract.

**Câu 6.** `try-with-resources` bao quanh đoạn chỉ lên lịch task async có luôn đúng không? **Không.** Resource có thể bị đóng trước khi task chạy xong.

## Ghi nhớ

- **Inject factory/provider bằng DI không đồng nghĩa container tự quản lý mọi instance do nó trả về.**
- Phân biệt **creator, consumer, owner** và thỏa thuận rõ **caller-owned, borrowed hoặc container-managed** cho từng resource.
- Dùng **try-with-resources** cho resource `AutoCloseable` thuộc caller trong thao tác đồng bộ, bảo đảm cleanup ở cả đường thành công và ngoại lệ.
- **Factory phải dọn tài nguyên chưa chuyển giao thành công**; composition root thường sở hữu pool/client dùng chung, còn từng consumer trả session theo scope của thao tác.
- Với **bất đồng bộ, scope khác nhau và dependency chia sẻ**, thời điểm đóng phải gắn với **lần sử dụng cuối cùng**. Kiểm thử các đường tạo, dùng, lỗi và đóng trước khi mở rộng sang DI container.
