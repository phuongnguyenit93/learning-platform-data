# Thứ tự giải phóng theo quan hệ phụ thuộc

Trong một ứng dụng Java dùng **Dependency Injection (DI)**, các đối tượng thường được lắp ghép theo một thứ tự dễ hiểu: tạo tài nguyên cơ sở trước, tạo cộng tác viên dựa trên tài nguyên đó sau, cuối cùng tạo thành phần nhận công việc. Khi dừng ứng dụng, nếu đóng tài nguyên cơ sở quá sớm, các đối tượng đang sử dụng nó có thể thất bại ngay trong quá trình dừng.

Ví dụ: một `JobWorker` cần `OrderRepository`, còn repository cần `ConnectionPool`. Khi khởi động, ta có thể tạo pool rồi repository rồi worker. Khi shutdown, cần **dừng worker trước khi đóng repository**, và **đóng repository trước khi đóng pool** nếu việc dọn dẹp repository còn cần pool hoạt động.

Đó là nguyên tắc trọng tâm của bài **Sở hữu tài nguyên**:

> Nếu A phụ thuộc vào B và cần B còn hoạt động để hoàn tất việc dừng hoặc giải phóng, hãy **dừng/đóng A trước, rồi mới đóng B**. Việc giải phóng thường diễn ra theo thứ tự ngược với các quan hệ phụ thuộc khi khởi tạo.

Nguyên tắc này cần đi cùng hai câu hỏi: **ai sở hữu tài nguyên**, và **tài nguyên đang được những ai sử dụng**. DI giúp làm rõ cách cung cấp dependency, còn composition root và cơ chế quản lý vòng đời phải giải quyết việc đóng tài nguyên đúng lúc. Ta sẽ thực hành bằng Java thuần trước khi liên hệ tới DI container.

## 1. Vì sao thứ tự đóng quan trọng?

Giả sử một ứng dụng xử lý job có đồ thị phụ thuộc:

```text
              Phụ thuộc khi hoạt động
      ┌────────────────────────────┐
      │ JobWorker                  │
      │   └── OrderRepository      │
      │         └── ConnectionPool │
      └────────────────────────────┘

      Tạo:   ConnectionPool → OrderRepository → JobWorker
      Đóng:  JobWorker → OrderRepository → ConnectionPool
```

Khi còn hoạt động, `JobWorker` dùng repository để lưu trạng thái job. Repository dùng connection từ pool để ghi dữ liệu. Nếu pool bị đóng trước, worker đang hoàn tất một job hoặc repository đang flush dữ liệu có thể nhận lỗi “connection pool closed”.

Với sơ đồ có hướng:

```text
A ──depends on──► B
```

thì cách hiểu thường là:

- **Tạo:** cần có B để xây hoặc cấu hình A.
- **Dùng:** A có thể gọi B khi xử lý công việc.
- **Giải phóng:** nếu A còn cần B trong lúc dừng, hãy đóng A rồi mới đóng B.

Đây là **quan hệ thứ tự một phần** giữa các đối tượng, không nhất thiết là một danh sách tuyến tính duy nhất. Với một object graph không có chu trình, có thể tạo theo thứ tự phù hợp với chiều phụ thuộc và đóng theo thứ tự ngược. Những đối tượng độc lập có thể được giải phóng theo nhiều thứ tự khác nhau.

Điều kiện “A cần B khi dừng” rất quan trọng: có những đối tượng không cần gọi dependency trong `close()`, nhưng vẫn phải **ngừng sử dụng** B trước khi B bị đóng. Nếu A có thread hoặc callback còn chạy, chỉ gọi `A.close()` mà không chờ nó thật sự ngừng có thể chưa đủ.

## 2. Sở hữu tài nguyên khác với việc giữ tham chiếu

Trong DI, một service có thể **nhận** một client hoặc pool qua constructor:

```java
final class NotificationService {
    private final MailClient client;

    NotificationService(MailClient client) {
        this.client = Objects.requireNonNull(client);
    }

    void send(String recipient, String message) {
        client.send(recipient, message);
    }
}
```

`NotificationService` sử dụng `MailClient`, nhưng từ việc inject **không thể suy ra** `NotificationService` sở hữu client và được phép đóng nó. Nếu một client dùng chung được cung cấp cho nhiều service, việc một service tự đóng client có thể phá hỏng các service còn lại.

Hãy tách ba vai trò:

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Owner (chủ sở hữu)** | Tạo hoặc tiếp nhận quyền sở hữu, quyết định khi nào đóng và chỉ đóng theo hợp đồng | Composition root quản lý pool ứng dụng |
| **Consumer (bên sử dụng)** | Gọi hành vi của dependency; tuân thủ thời gian sống của dependency | `NotificationService` dùng `MailClient` |
| **Borrower (bên mượn)** | Được dùng tài nguyên trong một phạm vi có hạn, thường phải trả về hoặc kết thúc quyền mượn theo API | Repository mượn connection từ pool |

Một đối tượng có thể đồng thời là consumer của tài nguyên này và owner của tài nguyên khác. Vì vậy **không dùng quy tắc máy móc “ai nhận vào constructor thì phải đóng”**. Quyền sở hữu phải được nói rõ ở constructor/factory/API và nơi lắp ghép.

### Hai cách cấp cùng một interface, nghĩa vụ đóng khác nhau

**Dependency dùng chung**:

```java
MailClient sharedClient = createMailClient();
NotificationService first = new NotificationService(sharedClient);
NotificationService second = new NotificationService(sharedClient);

// Composition root/chủ sở hữu đóng sharedClient ở shutdown,
// sau khi first và second đã dừng sử dụng nó.
```

**Tài nguyên cấp riêng cho một thao tác**:

```java
try (MailSession session = sessionFactory.open()) {
    session.send(recipient, message);
}
// session được trả về/đóng theo hợp đồng của factory.
```

Hai đoạn trên là **phác họa** với các kiểu do ứng dụng định nghĩa. Ở đoạn thứ hai, `try-with-resources` thể hiện bên nhận session có trách nhiệm kết thúc phạm vi dùng của nó. Không nên suy ra `MailClient.close()` hay `MailSession.close()` luôn có cùng tác dụng: với pool, lệnh “close connection” đôi khi chỉ trả connection về pool.

## 3. Thứ tự giải phóng của một đồ thị có nhiều nhánh

Hệ thống thực tế hiếm khi chỉ có một chuỗi thẳng. Giả sử:

```text
                  HttpListener
                       │
                       ▼
                  OrderService
                   /         \
                  ▼           ▼
           OrderRepository  AuditClient
                  │           │
                  └─────┬─────┘
                        ▼
                  ConnectionPool
```

`HttpListener` chỉ nhận request, `OrderService` gọi hai cộng tác viên, và cả repository lẫn audit client cùng dùng pool. Các ràng buộc quan trọng là:

- Phải **ngừng listener và chờ các request đang xử lý** trước khi đóng những service mà request cần.
- `OrderRepository` và `AuditClient` phải ngừng sử dụng pool trước khi pool đóng.
- Pool phải được **đóng một lần bởi owner**, cho dù nhiều consumer đang giữ tham chiếu tới nó.

Có thể có nhiều thứ tự đóng hợp lệ, ví dụ:

```text
HttpListener
  → OrderService
  → OrderRepository
  → AuditClient
  → ConnectionPool
```

hoặc đổi chỗ `OrderRepository` và `AuditClient` nếu chúng độc lập trong shutdown. Không cần áp đặt thứ tự giữa hai thành phần không có ràng buộc phụ thuộc.

Khi thiết kế quy trình shutdown, nên nhìn graph theo **quan hệ sử dụng và ownership**, thay vì đơn thuần đóng ngược tất cả trường trong một class bất kỳ.

### Mẹo hình dung

Nếu A có thể gọi B sau khi nhận lệnh dừng, B phải còn sẵn sàng cho tới khi A đã dừng hẳn.

```text
Đang nhận việc
    │
    ▼
[Ngừng tiếp nhận việc mới]
    │
    ▼
[Hoàn tất / hủy có kiểm soát công việc đang chạy]
    │
    ▼
[Đóng consumer phụ thuộc vào pool]
    │
    ▼
[Đóng pool và tài nguyên gốc]
```

Trong ứng dụng bất đồng bộ, giai đoạn “ngừng nhận” và “chờ công việc đang chạy” không thể thay bằng một biến `boolean` nếu còn callback, future hoặc thread đang hoạt động. Đây là quyết định lifecycle riêng của server, executor và message consumer.

## 4. Java giúp quản lý thứ tự bằng cách nào?

Java có giao diện `AutoCloseable` và câu lệnh `try-with-resources`:

```java
interface Resource extends AutoCloseable {
    @Override
    void close();
}
```

Giao diện con này thu hẹp chữ ký `close()` để ví dụ không cần khai báo checked exception. Với tài nguyên thực, `AutoCloseable.close()` có thể ném `Exception`, vì vậy code phải tuân theo hợp đồng API cụ thể.

Khi khai báo nhiều resource trong một `try-with-resources`, Java **tự đóng theo thứ tự ngược với thứ tự khai báo**:

```java
try (ConnectionPool pool = openPool();
     Repository repository = openRepository(pool);
     JobWorker worker = createWorker(repository)) {

    worker.runOneJob();
}
// Java gọi worker.close(), repository.close(), pool.close().
```

*Đây là pseudocode về thứ tự khi ba kiểu đều implement `AutoCloseable`; các hàm factory cần được định nghĩa trong ứng dụng.*

Cách này đặc biệt phù hợp cho một scope sở hữu vài tài nguyên có thứ tự tạo rõ ràng. Nó không tự giải quyết mọi tình huống:

- Nếu một tài nguyên không do scope hiện tại sở hữu, scope này **không nên đóng nó**.
- Nếu nhiều nhánh cùng dùng một tài nguyên chia sẻ, không đăng ký một instance ấy để đóng lặp ở nhiều owner.
- Nếu resource được tạo động hoặc trong nhiều nhánh điều kiện, có thể cần một lifecycle manager hoặc một ngăn xếp cleanup theo quyền sở hữu.
- Nếu dừng consumer mất thời gian hoặc là bất đồng bộ, cần đợi nó dừng theo hợp đồng trước khi trả về từ `close()` hoặc trước khi đóng dependency.

Điều quan trọng không phải cú pháp `try`, mà là các resource được cấp và giải phóng **theo cùng một hợp đồng ownership**.

## 5. Ví dụ Java thuần hoàn chỉnh: đóng theo thứ tự ngược khi lắp ghép

Ví dụ sau thực hành với một graph có ba tầng:

```text
Worker ──► Repository ──► Pool
```

Composition root tạo `Pool`, sau đó `Repository`, cuối cùng `Worker`. Một `ResourceOwner` giữ **ngăn xếp các tài nguyên do nó sở hữu**; tài nguyên được đăng ký ngay sau khi tạo thành công, và khi đóng sẽ được lấy ra theo nguyên tắc LIFO (*last in, first out*).

Mã được thiết kế để người học thấy thứ tự đóng qua danh sách sự kiện mà **không cần database thật**. Lưu toàn bộ vào `OwnershipOrderDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public final class OwnershipOrderDemo {

    // Ví dụ chọn close() không ném checked exception.
    interface Managed extends AutoCloseable {
        @Override
        void close();
    }

    static final class Pool implements Managed {
        private final List<String> events;
        private boolean closed;

        Pool(List<String> events) {
            this.events = Objects.requireNonNull(events);
            events.add("open pool");
        }

        void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("pool closed");
            }
        }

        @Override
        public void close() {
            if (!closed) {
                events.add("close pool");
                closed = true;
            }
        }
    }

    static final class Repository implements Managed {
        private final Pool pool;
        private final List<String> events;
        private boolean closed;

        Repository(Pool pool, List<String> events) {
            this.pool = Objects.requireNonNull(pool);
            this.events = Objects.requireNonNull(events);
            pool.ensureOpen();
            events.add("open repository");
        }

        void save(String id) {
            ensureOpen();
            pool.ensureOpen();
            events.add("save " + id);
        }

        void ensureOpen() {
            if (closed) {
                throw new IllegalStateException("repository closed");
            }
        }

        @Override
        public void close() {
            if (!closed) {
                // Ví dụ giả lập repository vẫn cần pool khi cleanup.
                pool.ensureOpen();
                events.add("close repository");
                closed = true;
            }
        }
    }

    static final class Worker implements Managed {
        private final Repository repository;
        private final List<String> events;
        private boolean closed;

        Worker(Repository repository, List<String> events) {
            this.repository = Objects.requireNonNull(repository);
            this.events = Objects.requireNonNull(events);
            repository.ensureOpen();
            events.add("create worker");
        }

        void execute(String id) {
            if (closed) {
                throw new IllegalStateException("worker closed");
            }
            repository.save(id);
        }

        @Override
        public void close() {
            if (!closed) {
                // Giả định worker kiểm tra repository trước khi dừng.
                repository.ensureOpen();
                events.add("close worker");
                closed = true;
            }
        }
    }

    // Quản lý đúng những tài nguyên mà composition root sở hữu.
    static final class ResourceOwner implements Managed {
        private final Deque<Managed> owned = new ArrayDeque<>();
        private boolean closed;

        <T extends Managed> T own(T resource) {
            Objects.requireNonNull(resource, "resource");
            if (closed) {
                throw new IllegalStateException("owner closed");
            }
            owned.push(resource); // Đăng ký sau khi resource tạo thành công.
            return resource;
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            closed = true;

            Throwable primary = null;

            // LIFO: worker, repository, pool.
            // Cố gắng đóng hết dù một close() thất bại.
            while (!owned.isEmpty()) {
                Managed resource = owned.pop();
                try {
                    resource.close();
                } catch (RuntimeException | Error failure) {
                    if (primary == null) {
                        primary = failure;
                    } else if (primary != failure) {
                        primary.addSuppressed(failure);
                    }
                }
            }

            if (primary instanceof RuntimeException failure) {
                throw failure;
            }
            if (primary instanceof Error failure) {
                throw failure;
            }
        }
    }

    static final class Application implements Managed {
        private final Worker worker;
        private final ResourceOwner owner;

        Application(Worker worker, ResourceOwner owner) {
            this.worker = Objects.requireNonNull(worker);
            this.owner = Objects.requireNonNull(owner);
        }

        void handle(String id) {
            worker.execute(id);
        }

        @Override
        public void close() {
            owner.close();
        }
    }

    // Composition root: lắp graph và xử lý startup thất bại.
    static Application bootstrap(
            List<String> events,
            boolean failAfterRepository) {

        ResourceOwner owner = new ResourceOwner();

        try {
            Pool pool = owner.own(new Pool(events));
            Repository repository = owner.own(
                new Repository(pool, events));

            // Giả lập startup check thất bại sau khi tạo 2 tài nguyên.
            if (failAfterRepository) {
                throw new IllegalStateException(
                    "startup check failed");
            }

            Worker worker = owner.own(new Worker(repository, events));
            return new Application(worker, owner);

        } catch (RuntimeException | Error startupFailure) {
            // Nếu startup lỗi, không trả về graph chưa hoàn chỉnh.
            try {
                owner.close();
            } catch (RuntimeException | Error cleanupFailure) {
                if (cleanupFailure != startupFailure) {
                    startupFailure.addSuppressed(cleanupFailure);
                }
            }
            throw startupFailure;
        }
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        try (Application app = bootstrap(events, false)) {
            app.handle("INV-1");
        }

        events.forEach(System.out::println);
    }
}
```

Biên dịch và chạy:

```bash
javac OwnershipOrderDemo.java
java OwnershipOrderDemo
```

Kết quả dự kiến:

```text
open pool
open repository
create worker
save INV-1
close worker
close repository
close pool
```

### Vì sao thứ tự đó đúng?

`ResourceOwner.own(...)` chỉ đăng ký resource **sau khi constructor resource đó trả về**. Việc tạo graph theo chiều phụ thuộc đưa `Pool` vào stack trước, sau đó `Repository`, rồi `Worker`. `Deque.push(...)` đặt phần tử mới lên đầu stack; `pop()` lấy phần tử mới nhất trước, nên kết quả đóng là worker → repository → pool.

Trong ví dụ, `Worker.close()` gọi `repository.ensureOpen()` và `Repository.close()` gọi `pool.ensureOpen()`. Nếu ta đóng pool trước repository, hoặc đóng repository trước worker, lỗi `IllegalStateException` sẽ xuất hiện. Những lần kiểm tra đó mô phỏng một cleanup thực tế còn cần dependency sống để flush dữ liệu hoặc hủy đăng ký callback.

Lệnh `Application.close()` chỉ gọi `owner.close()`. `Application` là ranh giới lifetime do caller sở hữu; `ResourceOwner` tập trung trách nhiệm đóng những resource của graph. Hai lần `close()` trong ví dụ là an toàn vì owner có cờ `closed`, nhưng **không nên mặc định mọi API close thực tế đều idempotent**.

### Phạm vi của ví dụ

Code cố ý **chạy tuần tự**. `events` là `ArrayList`, các cờ `closed` là `boolean`; chúng không dùng để quản lý shutdown khi request đang chạy trên nhiều thread. Nếu có executor hoặc listener thật, bước dừng nhận việc và chờ công việc hoàn tất phải được thiết kế trước khi đóng dependency bên dưới.

`Repository` trong ví dụ tự implements `Managed` để nhìn thấy thứ tự đóng. Trong hệ thống thực tế, repository thuần chỉ mượn `DataSource` có thể không cần `close()`; khi ấy chỉ cần dừng các consumer đang chạy và đóng pool tại đúng chủ sở hữu.

## 6. Kiểm thử thứ tự đóng và tình huống startup lỗi

Để xác minh cơ chế một cách độc lập, lưu `OwnershipOrderCheck.java` cùng thư mục với `OwnershipOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public final class OwnershipOrderCheck {
    public static void main(String[] args) {
        // Trường hợp 1: một phiên làm việc bình thường.
        List<String> normal = new ArrayList<>();

        try (OwnershipOrderDemo.Application app =
                OwnershipOrderDemo.bootstrap(normal, false)) {
            app.handle("INV-1");
        }

        List<String> normalExpected = List.of(
            "open pool",
            "open repository",
            "create worker",
            "save INV-1",
            "close worker",
            "close repository",
            "close pool"
        );

        if (!normal.equals(normalExpected)) {
            throw new AssertionError("Wrong normal order: " + normal);
        }

        // Trường hợp 2: khởi động thất bại sau khi có repository.
        List<String> failedStartup = new ArrayList<>();

        boolean failed = false;
        try {
            OwnershipOrderDemo.bootstrap(failedStartup, true);
        } catch (IllegalStateException expected) {
            failed = "startup check failed".equals(
                expected.getMessage());
        }

        if (!failed) {
            throw new AssertionError(
                "Expected startup check failure");
        }

        List<String> failedExpected = List.of(
            "open pool",
            "open repository",
            "close repository",
            "close pool"
        );

        if (!failedStartup.equals(failedExpected)) {
            throw new AssertionError(
                "Wrong failed-startup order: " + failedStartup);
        }

        // Trường hợp 3: close nhiều lần không đóng tài nguyên lặp.
        List<String> repeated = new ArrayList<>();
        OwnershipOrderDemo.Application app =
            OwnershipOrderDemo.bootstrap(repeated, false);

        app.close();
        app.close();

        if (!repeated.equals(List.of(
                "open pool",
                "open repository",
                "create worker",
                "close worker",
                "close repository",
                "close pool"))) {
            throw new AssertionError(
                "Resources were closed more than once");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac OwnershipOrderDemo.java OwnershipOrderCheck.java
java OwnershipOrderCheck
```

Kết quả dự kiến: `PASS`.

Ba tình huống này kiểm tra những ranh giới khác nhau. Đường bình thường kiểm tra thứ tự giải phóng theo quan hệ phụ thuộc. Startup thất bại kiểm tra rằng tài nguyên đã tạo không bị bỏ quên và không trả về một application nửa khởi tạo. Đóng lặp kiểm tra hợp đồng idempotent mà `ResourceOwner` của **ví dụ này** đã công bố.

Đây là kiểm thử trình tự bằng fake, không kiểm tra transaction, network I/O hay hành vi shutdown của thư viện ngoài. Với tài nguyên thật, cần thêm integration test cho timeout, cancellation, retry và close failure theo API cụ thể.

## 7. Nếu một bước khởi tạo thất bại giữa chừng?

Giả sử composition root đã mở `Pool` và tạo `Repository`, nhưng không khởi động được worker. Nếu chỉ ném exception, pool có thể vẫn giữ socket, thread hoặc file descriptor.

Nguyên tắc là: **mỗi tài nguyên được tạo thành công phải có một đường cleanup nếu bước tiếp theo thất bại**. Trong ví dụ, resource được đăng ký vào `ResourceOwner` ngay sau khi khởi tạo thành công. Khi xảy ra lỗi, composition root đóng stack đã có theo thứ tự ngược.

```text
Startup:
   1. Pool mở              ✔
   2. Repository tạo        ✔
   3. Worker/health check   ✘

Rollback startup:
   1. Đóng Repository
   2. Đóng Pool
   3. Giữ nguyên nguyên nhân khởi động thất bại
```

Một trường hợp tinh tế hơn là **constructor hoặc factory mở dở tài nguyên rồi ném lỗi trước khi trả instance**. Ví dụ factory mở socket nhưng lỗi khi cấu hình TLS. Caller chưa nhận được một `AutoCloseable` để đăng ký vào owner. Lúc này **factory phải tự dọn những phần đã cấp phát dở** bằng `try`/`finally` hoặc `try-with-resources` trước khi ném lỗi.

```java
// Minh họa ý tưởng trong một factory có tài nguyên trung gian.
Socket socket = openSocket();
try {
    return configureAndTransferOwnership(socket);
} catch (RuntimeException | Error failure) {
    try {
        socket.close();
    } catch (Exception cleanupFailure) {
        failure.addSuppressed(cleanupFailure);
    }
    throw failure;
}
```

Đoạn trên là **pseudocode**: `openSocket()` và `configureAndTransferOwnership(...)` do ứng dụng định nghĩa; ngoại lệ checked khi mở socket và hợp đồng chuyển quyền sở hữu cần được xử lý trong implementation thật. Nếu quá trình tạo thành công, factory phải bảo đảm chỉ có **một** owner chịu trách nhiệm cuối cùng đối với socket.

### Vì sao không đóng tất cả resource trong từng constructor?

Constructor của consumer thường chỉ nhận các dependency đã được tạo ở bên ngoài. Nó chưa phải chủ sở hữu chúng. Mỗi consumer tự đóng dependency khi thất bại có thể gây **double-close** hoặc đóng một pool đang được consumer khác sử dụng.

Với tài nguyên dùng chung, **composition root hoặc lifecycle manager** là vị trí dễ kiểm soát hơn để biết những resource nào đã cấp thành công và thứ tự cần dọn.

## 8. Nếu việc đóng cũng thất bại?

Một câu hỏi rất thực tế: lúc shutdown, `Worker.close()` ném exception. Có nên dừng ngay, bỏ qua repository và pool?

Nếu không cố gắng đóng tiếp, hệ thống có thể rò thêm tài nguyên. Nhưng nếu bắt mọi lỗi rồi bỏ qua hoàn toàn, ta mất thông tin sự cố. Cách thường hữu ích là:

1. Ghi nhớ lỗi đóng đầu tiên.
2. Tiếp tục **cố gắng** đóng những tài nguyên còn thuộc quyền sở hữu.
3. Gắn các lỗi đóng tiếp theo thành **suppressed exceptions**.
4. Báo lại lỗi theo chính sách vận hành.

`ResourceOwner.close()` trong ví dụ sử dụng đúng ý tưởng này. Khi `bootstrap(...)` thất bại, lỗi startup được giữ làm **lỗi chính**, còn lỗi cleanup được gắn dưới dạng suppressed.

Java `try-with-resources` cũng hỗ trợ suppressed exceptions: nếu thân `try` đã ném lỗi, lỗi từ `close()` thường không thay thế lỗi gốc mà được bổ sung vào nó. Điều này giúp xác định **nguyên nhân ban đầu** và các vấn đề phát sinh trong lúc dọn dẹp.

Ví dụ ngắn:

```java
try (AutoCloseable resource = () -> {
        throw new IllegalStateException("close failed");
    }) {
    throw new IllegalArgumentException("business failed");
} catch (IllegalArgumentException failure) {
    System.out.println(failure.getMessage()); // business failed
    System.out.println(
        failure.getSuppressed()[0].getMessage()); // close failed
}
```

Tài nguyên dùng để minh họa chỉ có callback `close()`; ví dụ không phụ thuộc hạ tầng bên ngoài.

**Không phải lúc nào cũng an toàn để tiếp tục tùy tiện sau lỗi cleanup.** Có những resource mà close thất bại khiến thành phần phụ thuộc khác rơi vào trạng thái không chắc chắn. Cần phân biệt mục tiêu *best-effort cleanup* với yêu cầu đảm bảo consistency, và luôn giữ log/tracing đủ để chẩn đoán.

## 9. Quy tắc với tài nguyên dùng chung và tài nguyên theo request

Trong ứng dụng web, thường tồn tại nhiều tầng ownership:

```text
Application owner
  ├── HttpListener
  ├── ConnectionPool     (dùng chung)
  └── RequestScope #1
        └── Connection   (mượn từ pool)
        └── UnitOfWork   (theo transaction)

  └── RequestScope #2
        └── Connection   (mượn từ pool)
        └── UnitOfWork   (theo transaction)
```

Scope là **ranh giới dùng và chia sẻ**, còn ownership cho biết **ai có quyền đóng**. Trong một mô hình phổ biến:

| Tài nguyên | Ai thường sở hữu? | Khi nào đóng? |
|---|---|---|
| Pool hoặc client thread-safe dùng chung | Application root / DI container | Sau khi đã dừng các consumer và request đang sử dụng |
| Connection mượn từ pool | Request/transaction boundary | Khi kết thúc thao tác; `close()` có thể mang nghĩa trả về pool |
| Unit of work/transaction | Phạm vi đơn vị công việc | Commit hoặc rollback theo hợp đồng, rồi giải phóng |
| HTTP listener hoặc queue consumer | Startup/shutdown coordinator | Ngừng tiếp nhận, drain in-flight work, rồi giải phóng |
| Đối tượng cấu hình bất biến | Không cần cleanup | Garbage collector xử lý bộ nhớ khi hết tham chiếu |

Một request không được tự ý đóng pool ứng dụng chỉ vì nó được inject pool. Ngược lại, application root không nên đóng connection của một transaction đang chạy mà chưa có chính sách kết thúc request tương ứng.

Một quy trình shutdown điển hình:

```text
Tắt readiness / ngừng nhận request mới
                   ↓
Chờ các request đang chạy kết thúc (có giới hạn)
                   ↓
Đóng request/transaction resources còn thuộc quyền quản lý
                   ↓
Dừng các thành phần nền, flush theo hợp đồng
                   ↓
Đóng pool/client dùng chung
                   ↓
Hoàn tất shutdown
```

Nếu hết deadline mà vẫn còn request, cần quy định rõ hành vi hủy, rollback và lỗi trả về. Đó là chính sách của hệ thống, không thể giải quyết chỉ bằng việc gọi `close()` theo thứ tự.

## 10. Constructor injection, factory và vòng đời trong object graph

**Constructor injection** làm rõ cộng tác viên cần thiết:

```java
final class ReportWorker {
    private final ReportRepository repository;

    ReportWorker(ReportRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }
}
```

Nhưng constructor injection **không tự xác định ai đóng repository**. Nếu composition root tạo repository và truyền cho worker, root phải biết repository có sở hữu tài nguyên riêng hay chỉ mượn `DataSource`.

Nếu mỗi lời gọi cần một tài nguyên ngắn hạn, có thể inject factory:

```java
interface UnitOfWork extends AutoCloseable {
    void save(String id);

    @Override
    void close();
}

interface UnitOfWorkFactory {
    UnitOfWork open();
}

final class SaveService {
    private final UnitOfWorkFactory factory;

    SaveService(UnitOfWorkFactory factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    void save(String id) {
        try (UnitOfWork work = factory.open()) {
            work.save(id);
        }
    }
}
```

*Đây là ví dụ độc lập về thiết kế khi các kiểu đã được nhập/định nghĩa trong cùng đơn vị mã.* `SaveService` nhận factory qua constructor, còn `UnitOfWork` được mở theo từng lần xử lý và đóng trong `try-with-resources`. Factory có thể dùng pool cấp ứng dụng ở phía sau, nhưng service không cần sở hữu pool.

Lưu ý: **đóng UnitOfWork không tự chứng minh transaction đã commit đúng**. Hợp đồng sản xuất cần nói rõ thành công, rollback, ngoại lệ và thứ tự flush/commit/close.

Nếu dùng DI container, nó có thể sở hữu các instance tạo ra, quản lý scoped bean hoặc gọi callback khi context đóng. Tuy vậy, ngữ nghĩa destroy, thứ tự shutdown và cách xử lý disposable transient khác nhau giữa framework. Trước khi đăng ký `AutoCloseable` hoặc bean có hook `destroy()`, cần xác định **ai là owner** và container có thực sự bảo đảm thứ tự giải phóng cần thiết không.

## 11. Dùng đồ thị phụ thuộc để lập kế hoạch shutdown

Với ứng dụng lớn, có thể ghi lại một bảng đơn giản để tránh đóng sai:

| Thành phần | Phụ thuộc vào | Ai sở hữu | Điều kiện trước khi đóng |
|---|---|---|---|
| `QueueConsumer` | `JobHandler` | Application | Dừng poll và chờ job đang xử lý |
| `JobHandler` | `Repository`, `AuditClient` | Application hoặc request scope | Không còn request/job đang dùng |
| `Repository` | `ConnectionPool` | Application/request theo implementation | Hoàn tất transaction và flush cần thiết |
| `AuditClient` | `HttpClient` | Application | Hoàn tất hoặc hủy các bản ghi đang gửi |
| `ConnectionPool` | Không có dependency ứng dụng | Application | Không còn borrower dùng connection |
| `HttpClient` | Không có dependency ứng dụng | Application | Không còn request nền cần client |

Từ bảng trên, ta xác định được ràng buộc `QueueConsumer` → `JobHandler` → `Repository` → `ConnectionPool` và `JobHandler` → `AuditClient` → `HttpClient`. Đóng theo thứ tự ngược quan hệ phụ thuộc, đồng thời xử lý rõ các job chưa hoàn tất.

Ở graph không có chu trình, thứ tự đóng phù hợp có thể được suy ra từ thứ tự tôpô đảo của quan hệ *consumer phụ thuộc vào provider*. Một **stack LIFO** thuận tiện nếu mọi tài nguyên được tạo, đăng ký theo thứ tự dependency trước consumer và không có ownership chồng chéo. Với graph động, nhiều module và tài nguyên dùng chung, stack đơn giản có thể chưa đủ: lifecycle manager cần biết quan hệ và ranh giới ownership thực tế.

### Nếu phát hiện chu trình phụ thuộc?

Ví dụ `ServiceA` cần `ServiceB`, nhưng `ServiceB` cũng cần `ServiceA` để shutdown. Khi không xác định được cái nào phải đóng trước, nên xem lại trách nhiệm và hợp đồng vòng đời. Có thể cần tách thành nhiều giai đoạn:

1. **Stop accepting:** tất cả thành phần ngừng tạo công việc mới.
2. **Quiesce/drain:** hoàn tất công việc đang chạy, ngừng callback.
3. **Dispose:** đóng tài nguyên nền khi không còn bên sử dụng.

Thiết kế theo giai đoạn có thể giải quyết ràng buộc thực tế tốt hơn việc gọi `close()` đệ quy giữa hai service. Không nên giấu chu trình bằng global registry hoặc phụ thuộc vào thứ tự ngẫu nhiên.

## 12. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Đóng pool trước consumer | Consumer đang dừng nhưng còn cần pool | Stop/drain consumer trước, pool sau |
| Service tự đóng collaborator được inject dù không sở hữu | Các service khác mất dependency dùng chung | Quy định owner tại composition root |
| Mỗi request đóng một singleton client | Tài nguyên ứng dụng bị đóng quá sớm | Request chỉ đóng tài nguyên của request |
| Khởi động thất bại nhưng bỏ qua resource đã tạo | Rò socket, thread hoặc connection | Đăng ký ownership sau mỗi bước tạo thành công và cleanup khi lỗi |
| Constructor/factory ném lỗi sau khi mở dở tài nguyên | Caller không có instance để đóng | Factory tự cleanup phần cấp phát chưa chuyển quyền sở hữu |
| Một `close()` lỗi thì bỏ qua các resource còn lại | Tài nguyên khác không được giải phóng | Cố gắng cleanup các resource thuộc quyền sở hữu và giữ suppressed errors |
| Đóng một resource chia sẻ ở nhiều owner | Double-close, trạng thái bất định | Một ownership rõ ràng, consumer chỉ mượn |
| Gọi `close()` mà không chờ thread/callback ngừng | Task vẫn chạy và dùng dependency đã đóng | Đặt shutdown gate và quiescence trước disposal |
| Trông cậy vào garbage collector để đóng socket | Tài nguyên không được giải phóng đúng hạn | Dùng `AutoCloseable` và lifecycle rõ |
| Cho rằng container tự bảo đảm mọi thứ tự đóng | Lỗi chỉ lộ khi shutdown hoặc rollout | Kiểm tra lifecycle framework và integration test |

## 13. Bài tập thực hành

**Bài tập 1 — Vẽ lại chiều phụ thuộc.** Có `HttpListener`, `OrderService`, `OrderRepository` và `DataSource`. Vẽ cạnh A → B khi A dùng B, xác định thứ tự tạo và thứ tự dừng/đóng phù hợp. Nêu rõ listener phải ngừng nhận request và drain trước khi đóng repository.

**Bài tập 2 — Thêm nhánh dùng chung.** Trong `OwnershipOrderDemo`, thêm `AuditReporter` cũng dùng `Pool`. Đăng ký reporter vào `ResourceOwner` sau pool, rồi thêm một consumer dùng reporter. Theo dõi thứ tự đóng và bảo đảm pool chỉ đóng một lần dù có hai nhánh.

**Bài tập 3 — Thử đóng sai.** Trong một bản sao riêng của ví dụ, thay thứ tự đóng thành pool trước repository. Quan sát `IllegalStateException` và giải thích hành vi nào của repository vẫn cần pool sống. Khôi phục thứ tự hợp lệ sau khi tìm hiểu.

**Bài tập 4 — Gây lỗi cleanup.** Tạo một `Managed` có `close()` ném `IllegalStateException` và một `Managed` khác ghi nhận việc đóng vào danh sách. Đăng ký cả hai trong owner, gọi `close()` và kiểm tra resource thứ hai vẫn được thử đóng, lỗi chính vẫn được báo.

**Bài tập 5 — Startup thất bại nhiều bước.** Mở thêm một resource trung gian trước khi tạo worker, sau đó mô phỏng lỗi trong bước cuối. Kiểm tra những resource đã tạo thành công đều được đóng theo thứ tự ngược và không có instance ứng dụng chưa hoàn chỉnh bị trả ra.

**Bài tập 6 — Phân biệt sở hữu và mượn.** Một `Repository` nhận `DataSource` do composition root tạo, còn `save(...)` mượn `Connection` từ pool. Giải thích vì sao repository thường chỉ đóng connection của thao tác, không đóng `DataSource` dùng chung.

### Câu hỏi tự kiểm tra

1. Nếu A còn dùng B trong quá trình shutdown, thứ tự đóng nên là A rồi B hay B rồi A?
2. Constructor nhận một `AutoCloseable` có khiến consumer trở thành owner không?
3. Vì sao cần đóng các nhánh consumer trước khi đóng tài nguyên dùng chung?
4. Khi startup ném lỗi sau khi tạo hai resource, phần nào chịu trách nhiệm đóng chúng?
5. Nếu factory mở dở socket rồi ném exception trước khi trả instance, ai phải cleanup?
6. Tại sao `try-with-resources` có ích khi nhiều tài nguyên được khai báo theo thứ tự phụ thuộc?
7. Khi một `close()` ném lỗi, làm thế nào bảo toàn lỗi ban đầu và vẫn thử cleanup?
8. Vì sao shutdown của hệ thống async cần thêm bước dừng nhận việc và drain?

**Gợi ý:** (1) A trước B; (2) không, ownership phải có hợp đồng; (3) để không còn consumer sử dụng tài nguyên đã đóng; (4) composition root/lifecycle owner; (5) factory; (6) Java đóng ngược thứ tự khai báo; (7) giữ primary exception, gắn suppressed và dọn best effort; (8) callback/thread có thể vẫn sử dụng dependency sau khi close được gọi.

## Ghi nhớ

- **Giải phóng theo quan hệ phụ thuộc:** consumer phải dừng sử dụng dependency trước khi dependency bị đóng; với graph đơn giản, thứ tự đóng thường ngược thứ tự tạo.
- **Ownership khác với injection:** nhận dependency qua constructor chỉ có nghĩa được sử dụng; không tự có quyền đóng dependency.
- **Tài nguyên dùng chung có một owner rõ ràng** và chỉ được đóng sau khi mọi bên sử dụng kết thúc; tài nguyên theo request/transaction được đóng tại ranh giới scope tương ứng.
- **Startup thất bại cần cleanup một phần:** tài nguyên đã tạo thành công phải được giải phóng; factory chịu trách nhiệm với phần tạo dở chưa bàn giao.
- **Đóng có thể thất bại:** cố gắng giải phóng các tài nguyên còn lại và giữ nguyên lỗi chính cùng suppressed exceptions để chẩn đoán.
- **DI thủ công giúp nhìn rõ vòng đời:** composition root tạo và sở hữu object graph; DI container có thể hỗ trợ lifecycle nhưng vẫn cần kiểm chứng thứ tự và hợp đồng giải phóng.
