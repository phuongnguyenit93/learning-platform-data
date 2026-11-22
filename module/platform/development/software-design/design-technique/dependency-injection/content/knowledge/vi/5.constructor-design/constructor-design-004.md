# Phân biệt kiểm tra đầu vào với thực hiện kết nối hoặc nghiệp vụ khi khởi tạo

Trong thiết kế **Dependency Injection (DI)**, constructor thường là nơi đối tượng nhận các cộng tác viên bắt buộc. Nhưng nhận phụ thuộc không có nghĩa là **dùng ngay phụ thuộc để kết nối mạng, truy vấn cơ sở dữ liệu hay xử lý một tác vụ nghiệp vụ**.

Hãy hình dung `InvoiceNotifier` cần một thành phần gửi thư. Có hai yêu cầu hoàn toàn khác nhau:

- Khi tạo `InvoiceNotifier`, cần chắc chắn thành phần gửi thư đã được cung cấp và cấu hình cơ bản hợp lệ.
- Khi có yêu cầu gửi hóa đơn, mới cần mở kết nối cần thiết, gửi nội dung, xử lý lỗi và giải phóng tài nguyên.

Đặt cả hai việc trong constructor sẽ làm mờ ranh giới **khởi tạo trạng thái hợp lệ** và **thực thi tác vụ có tác dụng phụ (side effect)**. Bài học này phân biệt rõ các trách nhiệm đó, liên hệ với *constructor injection*, *composition root*, scope và vòng đời đối tượng, rồi thực hành bằng Java thuần trước khi sử dụng DI container.

## 1. Constructor nên bảo đảm điều gì?

Với một lớp thông thường nhận phụ thuộc qua constructor, mục tiêu thiết kế hữu ích là:

> Sau khi constructor trả về thành công, đối tượng ở trạng thái hợp lệ theo các bất biến của chính nó và sẵn sàng được sử dụng theo hợp đồng đã công bố.

Trong thực tế, constructor thường làm ba việc:

1. **Nhận collaborator bắt buộc:** chẳng hạn `MailSessionFactory`, `OrderRepository`, `Clock` hoặc `PricingPolicy`. Việc lựa chọn implementation do nơi lắp ghép quyết định.
2. **Kiểm tra điều kiện cục bộ:** tham số bắt buộc khác `null`, tên cấu hình không rỗng, timeout dương, giới hạn hợp lý, các trường có quan hệ nhất quán.
3. **Gán trạng thái và tính giá trị dẫn xuất thuần túy:** lưu các trường `final`, sao chép collection để bảo vệ bất biến, chuẩn hóa biểu diễn dữ liệu khi có hợp đồng rõ ràng.

Các việc này có thể thực hiện mà không cần liên hệ tới hệ thống bên ngoài. Ví dụ:

```java
import java.util.List;
import java.util.Objects;

final class DispatchSettings {
    private final String sender;
    private final int maxAttempts;
    private final List<String> channels;

    DispatchSettings(String sender, int maxAttempts, List<String> channels) {
        if (sender == null || sender.isBlank()) {
            throw new IllegalArgumentException("sender must not be blank");
        }
        if (maxAttempts < 1 || maxAttempts > 5) {
            throw new IllegalArgumentException("maxAttempts must be 1..5");
        }

        this.sender = sender;
        this.maxAttempts = maxAttempts;
        this.channels = List.copyOf(Objects.requireNonNull(channels));
    }
}
```

`List.copyOf(...)` tạo bản sao không cho phép sửa đổi từ bên ngoài và từ chối phần tử `null`. Đây là thao tác **bảo vệ bất biến của đối tượng**, không phải truy cập tài nguyên ngoài tiến trình.

Không phải constructor nào cũng phải thuần túy tuyệt đối: tạo giá trị dẫn xuất hay đối tượng phụ trợ nội bộ là bình thường. Điều quan trọng là **chi phí, tác dụng phụ và việc sở hữu tài nguyên phải dễ hiểu, có chủ đích**.

## 2. Kiểm tra đầu vào khác xác minh trạng thái của thế giới bên ngoài

Cùng được gọi là “validation”, nhưng các thao tác sau có ý nghĩa rất khác nhau.

| Thao tác | Ví dụ | Phù hợp trong constructor? | Lý do |
|---|---|---|---|
| Kiểm tra null | `Objects.requireNonNull(gateway)` | Thường có | Đảm bảo collaborator bắt buộc hiện diện |
| Kiểm tra phạm vi | `timeoutMs > 0` | Thường có | Bất biến của cấu hình |
| Kiểm tra cú pháp cục bộ | Parse một URI bằng thư viện chỉ xử lý chuỗi | Có thể | Không cần I/O; báo lỗi cấu hình sớm |
| Sao chép dữ liệu | `List.copyOf(routes)` | Thường có | Tránh caller thay đổi cấu hình sau khi tạo |
| Kiểm tra tồn tại qua network | Gọi API “tenant có tồn tại không?” | Thường không | Kết quả phụ thuộc mạng, trạng thái bên ngoài và thời điểm |
| Kiểm tra credential còn hiệu lực | Gọi dịch vụ xác thực | Nên đặt ở startup/readiness hoặc luồng sử dụng rõ ràng | Có I/O, timeout và lỗi vận hành |
| Mở socket hoặc kết nối DB | `connect()`, `dataSource.getConnection()` | Cân nhắc chuyển ra lifecycle/method/factory | Đòi hỏi quản lý thời gian sống, lỗi và đóng tài nguyên |
| Gửi thư, trừ tiền, ghi đơn | `send()`, `charge()`, `save()` | Không nên là tác vụ ẩn khi khởi tạo service | Đây là hành vi nghiệp vụ cần một lệnh gọi có chủ ý |

**Kiểm tra hợp lệ cục bộ** trả lời: “Tham số của đối tượng có thỏa mãn hợp đồng không?”  
**Kiểm tra khả dụng bên ngoài** trả lời: “Dịch vụ/tài nguyên bên ngoài có đáp ứng tại thời điểm này không?”  
**Thực hiện nghiệp vụ** trả lời: “Đã có yêu cầu thực thi thao tác cụ thể nào?”

Ví dụ `databaseUrl` có cú pháp đúng không thể chứng minh database đang hoạt động. Ngược lại, kiểm tra kết nối thành công lúc khởi động cũng không đảm bảo kết nối vẫn còn sống khi request tiếp theo đến.

## 3. Khi constructor làm quá nhiều việc

Xét một phiên bản `InvoiceNotifier` có hành vi ẩn trong constructor:

```java
// Pseudocode minh họa phản ví dụ; SmtpClient do ứng dụng tự định nghĩa.
final class InvoiceNotifier {
    private final SmtpClient client;

    InvoiceNotifier(String host, int port, String testRecipient) {
        if (host == null || host.isBlank() || port <= 0) {
            throw new IllegalArgumentException("Invalid SMTP configuration");
        }

        client = new SmtpClient(host, port);  // Chọn implementation ở đây.
        client.connect();                      // I/O khi khởi tạo.
        client.send(testRecipient, "Ready");   // Hành vi gửi thư khi khởi tạo.
    }
}
```

Đoạn này trộn ít nhất bốn trách nhiệm: kiểm tra tham số, chọn implementation, kết nối dịch vụ và gửi thư. Nó dẫn tới những vấn đề cụ thể:

- **Khó dự đoán chi phí khởi tạo:** tạo một đối tượng bỗng có thể chờ DNS, TCP, TLS hoặc timeout.
- **Lỗi phát sinh ở thời điểm khó kiểm soát:** nơi gọi `new InvoiceNotifier(...)` có thể gặp sự cố mạng dù chưa yêu cầu gửi thư.
- **Khó kiểm thử độc lập:** test constructor có thể gây kết nối thật và gửi thư thật.
- **Không rõ ai sở hữu tài nguyên:** nếu `connect()` hoặc `send()` thất bại sau khi tạo client, đường giải phóng tài nguyên cần được thiết kế rõ; không thể trông chờ destructor tự chạy.
- **Làm rối object graph:** composition root hoặc DI container khó tạo service ổn định khi việc tạo đối tượng phụ thuộc vào trạng thái bên ngoài.
- **Tác dụng phụ khó phát hiện:** tạo nhiều instance có thể gửi nhiều thư; cơ chế retry khi khởi tạo thất bại có thể lặp tác vụ ngoài ý muốn.

Đây không phải khẳng định mọi thao tác I/O trong constructor đều bất hợp pháp. Có các lớp được thiết kế chuyên biệt để **sở hữu một tài nguyên** ngay từ khi tạo. Khi đó constructor phải có hợp đồng sở hữu, lỗi và giải phóng tài nguyên rất rõ. Với một **dịch vụ nghiệp vụ có thể tái sử dụng**, giữ constructor tập trung vào lắp ghép và bất biến thường dễ bảo trì hơn.

## 4. Ví dụ Java thuần: tách lắp ghép và gửi thư

Ta thiết kế lại để service nhận một `MailSessionFactory` qua constructor. Factory cung cấp session khi có lệnh gửi. Dữ liệu hóa đơn và người nhận thuộc **từng lần gọi**, không bị lưu vào service dùng chung.

Luồng hoạt động:

```text
                 Thời điểm lắp ghép
 Composition root ──► MailSessionFactory
          │                     │
          └──► InvoiceNotifier ─┘
               (kiểm tra và lưu phụ thuộc)
                       │
             Không mở session ở đây
                       │
                       ▼
                Thời điểm xử lý
        SendInvoiceCommand của request
                       │
                       ▼
          InvoiceNotifier.notifyInvoice()
                       │
                       ├── factory.open() → MailSession
                       ├── session.send(...)
                       └── session.close() khi kết thúc
```

Lưu ví dụ hoàn chỉnh dưới tên `InvoiceNotificationDemo.java` (Java 17 trở lên):

```java
import java.util.Objects;

public final class InvoiceNotificationDemo {

    // Dữ liệu của một lần gửi hóa đơn.
    record SendInvoiceCommand(String invoiceId, String recipient) {
        SendInvoiceCommand {
            requireText(invoiceId, "invoiceId");
            requireText(recipient, "recipient");
        }
    }

    // Tài nguyên có vòng đời ngắn, phải đóng sau khi dùng.
    interface MailSession extends AutoCloseable {
        void send(String sender, String recipient, String content);

        @Override
        void close();
    }

    // Collaborator mô tả cách tạo session cho từng thao tác.
    @FunctionalInterface
    interface MailSessionFactory {
        MailSession open();
    }

    static final class InvoiceNotifier {
        private final MailSessionFactory sessions;
        private final String senderAddress;

        InvoiceNotifier(MailSessionFactory sessions, String senderAddress) {
            // Chỉ kiểm tra hợp đồng cục bộ và gán trạng thái.
            this.sessions = Objects.requireNonNull(sessions, "sessions");
            this.senderAddress = requireText(senderAddress, "senderAddress");
        }

        void notifyInvoice(SendInvoiceCommand command) {
            Objects.requireNonNull(command, "command");

            // Chỉ lời gọi nghiệp vụ mới yêu cầu tài nguyên.
            try (MailSession session = sessions.open()) {
                session.send(
                    senderAddress,
                    command.recipient(),
                    "Invoice " + command.invoiceId()
                );
            }
        }
    }

    // Minh họa I/O bằng console; không cần SMTP thật.
    static final class ConsoleMailSessionFactory
            implements MailSessionFactory {
        @Override
        public MailSession open() {
            System.out.println("OPEN session");
            return new MailSession() {
                @Override
                public void send(
                        String sender, String recipient, String content) {
                    System.out.printf(
                        "SEND from=%s to=%s content=%s%n",
                        sender, recipient, content
                    );
                }

                @Override
                public void close() {
                    System.out.println("CLOSE session");
                }
            };
        }
    }

    private static String requireText(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return text;
    }

    public static void main(String[] args) {
        // Composition root: tạo và lắp collaborator.
        MailSessionFactory sessions = new ConsoleMailSessionFactory();
        InvoiceNotifier notifier =
                new InvoiceNotifier(sessions, "billing@example.org");

        System.out.println("CREATED notifier");

        // Chỉ đến đây mới mở session và thực hiện nghiệp vụ.
        notifier.notifyInvoice(
            new SendInvoiceCommand("INV-100", "customer@example.org")
        );
    }
}
```

Biên dịch và chạy:

```bash
javac InvoiceNotificationDemo.java
java InvoiceNotificationDemo
```

Kết quả dự kiến:

```text
CREATED notifier
OPEN session
SEND from=billing@example.org to=customer@example.org content=Invoice INV-100
CLOSE session
```

Sự xuất hiện của `CREATED notifier` **trước** `OPEN session` cho thấy constructor không mở session. `InvoiceNotifier` có thể được tạo và kiểm tra cấu hình trong lúc lắp ghép; việc kết nối/gửi xảy ra khi caller thực sự yêu cầu `notifyInvoice`.

Một số điểm thiết kế cần đọc đúng:

- `MailSessionFactory` là **collaborator**, được inject vào constructor. Đây là **constructor injection** bằng Java thuần, không cần container.
- `senderAddress` là **cấu hình ổn định của đối tượng**, nên vẫn có thể đi vào constructor dù không phải dịch vụ hành vi.
- `SendInvoiceCommand` là **dữ liệu của lần gọi**. Mỗi request có thể gửi đến người nhận và hóa đơn khác nhau mà không tạo lại service.
- `MailSession` có **vòng đời ngắn**. `try-with-resources` gọi `close()` sau khi gửi xong hoặc khi `send(...)` ném exception.
- `ConsoleMailSessionFactory` chỉ là implementation minh họa. Trong sản phẩm thực tế, implementation có thể dùng SMTP, HTTP client hoặc pool; cách cấp và đóng session phải phù hợp hợp đồng cụ thể của tài nguyên đó.

Trong ví dụ, kiểm tra chuỗi không rỗng **không phải xác thực email đầy đủ**. Xác thực địa chỉ, phân quyền người nhận, tình trạng hóa đơn và điều kiện gửi cần được thiết kế ở lớp thích hợp, không suy ra chỉ từ phép kiểm tra constructor.

## 5. Kiểm thử chứng minh constructor không tự kết nối

Có thể kiểm chứng thời điểm tạo tài nguyên bằng fake, không cần gọi mạng hoặc khởi động DI container. Lưu mã sau thành `InvoiceNotificationCheck.java` cạnh file ví dụ:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class InvoiceNotificationCheck {
    public static void main(String[] args) {
        AtomicInteger opens = new AtomicInteger();
        AtomicInteger closes = new AtomicInteger();
        AtomicReference<String> lastSent = new AtomicReference<>();
        AtomicBoolean shouldFail = new AtomicBoolean(false);

        InvoiceNotificationDemo.MailSessionFactory fake = () -> {
            opens.incrementAndGet();
            return new InvoiceNotificationDemo.MailSession() {
                @Override
                public void send(
                        String sender, String recipient, String content) {
                    lastSent.set(sender + "|" + recipient + "|" + content);
                    if (shouldFail.get()) {
                        throw new IllegalStateException("send failed");
                    }
                }

                @Override
                public void close() {
                    closes.incrementAndGet();
                }
            };
        };

        var notifier = new InvoiceNotificationDemo.InvoiceNotifier(
            fake, "billing@example.org"
        );

        // Bất biến đầu vào được kiểm tra, nhưng chưa mở session.
        if (opens.get() != 0) {
            throw new AssertionError("Constructor opened a session");
        }

        notifier.notifyInvoice(
            new InvoiceNotificationDemo.SendInvoiceCommand(
                "INV-7", "reader@example.org"
            )
        );

        if (opens.get() != 1 || closes.get() != 1) {
            throw new AssertionError("Session lifecycle was incorrect");
        }
        if (!"billing@example.org|reader@example.org|Invoice INV-7"
                .equals(lastSent.get())) {
            throw new AssertionError("Wrong request data");
        }

        // Khi gửi lỗi, session vẫn phải được đóng.
        shouldFail.set(true);
        try {
            notifier.notifyInvoice(
                new InvoiceNotificationDemo.SendInvoiceCommand(
                    "INV-8", "reader@example.org"
                )
            );
            throw new AssertionError("Expected send to fail");
        } catch (IllegalStateException expected) {
            if (!"send failed".equals(expected.getMessage())) {
                throw expected;
            }
        }

        if (opens.get() != 2 || closes.get() != 2) {
            throw new AssertionError("Failed send leaked a session");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac InvoiceNotificationDemo.java InvoiceNotificationCheck.java
java InvoiceNotificationCheck
```

Kết quả dự kiến: `PASS`.

Kiểm thử này tách được ba điều: constructor **không mở tài nguyên**, thao tác nghiệp vụ **dùng dữ liệu của lời gọi hiện tại**, và session **được đóng kể cả khi gửi thất bại**. Đây là một lợi ích trực tiếp khi tách việc lắp ghép và vòng đời phụ thuộc ra khỏi nghiệp vụ.

Lưu ý: nếu chính `sessions.open()` thất bại trước khi trả về một session hợp lệ, khối `try-with-resources` không có session để đóng; **factory chịu trách nhiệm dọn những tài nguyên đã cấp phát một phần trong quá trình mở**. Ngoài ra, khi `close()` cũng ném lỗi, Java có cơ chế suppressed exception; code sản xuất cần xử lý và ghi log theo hợp đồng tài nguyên.

## 6. “Fail fast” không có nghĩa phải kết nối trong constructor

“Fail fast” là nguyên tắc phát hiện lỗi sớm **tại thời điểm phù hợp**. Cần phân biệt:

**Lỗi cấu hình cục bộ:** service không được tạo nếu một tham số bắt buộc vắng mặt, timeout không hợp lệ hoặc các trường cấu hình mâu thuẫn. Constructor có thể và thường nên từ chối ngay.

```java
final class RetryPolicy {
    private final int attempts;

    RetryPolicy(int attempts) {
        if (attempts < 1 || attempts > 10) {
            throw new IllegalArgumentException("attempts must be 1..10");
        }
        this.attempts = attempts;
    }
}
```

**Lỗi khả dụng của hạ tầng:** cơ sở dữ liệu ngừng hoạt động, DNS thất bại, credential bị thu hồi hoặc một endpoint timeout. Những lỗi này nên được kiểm tra bằng **startup initialization**, **readiness check** hoặc ngay trong **thao tác sử dụng**, tùy yêu cầu sản phẩm.

Một ứng dụng cần từ chối phục vụ nếu database chưa sẵn sàng có thể thực hiện kiểm tra kết nối **một cách tường minh tại startup**, sau khi đã lắp ghép object graph:

```java
// Pseudocode của composition root.
DatabaseConfig config = readAndValidateConfig();
ConnectionProvider provider = new ConnectionProvider(config);
OrderRepository repository = new JdbcOrderRepository(provider);
OrderService service = new OrderService(repository);

// Kiểm tra hạ tầng theo chính sách startup, sau khi lắp ghép.
// startupChecks.verifyDatabase(provider); // Có thể timeout và báo lỗi.

// Chỉ khi đủ điều kiện mới đánh dấu ứng dụng sẵn sàng nhận request.
// server.markReady(service);
```

Đoạn minh họa này giả định các lớp hạ tầng đã được định nghĩa, không phải file Java chạy độc lập. Tác dụng của nó là **đặt tên và vị trí rõ ràng** cho kiểm tra hạ tầng. Việc xác nhận “healthy lúc startup” vẫn chỉ là ảnh chụp tại một thời điểm; lúc vận hành cần chính sách retry, timeout, circuit breaker hoặc xử lý lỗi thích hợp.

Khi dùng DI container, vòng đời bean có thể gồm constructor, injection, hook khởi tạo và hook hủy. Có thể chuyển I/O bắt buộc sang hook khởi tạo **nếu framework và hợp đồng startup cho phép**, song điều đó không tự động làm an toàn hơn: phải quyết định timeout, xử lý lỗi, thứ tự khởi động và cách rollback tài nguyên đã mở.

## 7. Phân biệt trách nhiệm theo vòng đời

Một hệ thống có thể có nhiều thời điểm hợp lệ để thực hiện tác vụ, và chúng không trùng nhau:

| Thời điểm | Mục đích chính | Ví dụ |
|---|---|---|
| Constructor | Xây đối tượng thỏa bất biến cục bộ | Nhận `OrderRepository`, kiểm tra `retryLimit` |
| Composition root | Chọn implementation và lắp object graph | `new OrderService(repository)` |
| Startup/init có chủ đích | Chuẩn bị tài nguyên dùng chung hoặc kiểm tra khả dụng | Khởi động pool, preload cache cần thiết |
| Lời gọi nghiệp vụ | Thực hiện yêu cầu cụ thể | `placeOrder(request)`, `sendInvoice(command)` |
| Request/transaction scope | Cấp và đóng tài nguyên cho một đơn vị công việc | Mở session, commit/rollback, đóng connection |
| Shutdown/close | Giải phóng tài nguyên dài hạn do thành phần sở hữu | Đóng pool, stop worker, flush có giới hạn |

Không phải tất cả hệ thống đều cần đủ sáu giai đoạn. Trong ứng dụng Java nhỏ, `main` có thể là composition root và kết thúc sau vài lời gọi. Trong ứng dụng web, có thể có container quản lý scope. Điều quan trọng là **không dùng constructor như một điểm khởi chạy nghiệp vụ ngầm định**.

### Sở hữu tài nguyên: ai mở thì ai đóng?

Quy tắc thực hành là quyền sở hữu phải rõ trong hợp đồng, thay vì đoán từ tên biến:

- Nếu factory cấp một session mà caller sở hữu, phương thức dùng session cần đóng sau khi xong, như `try-with-resources` ở ví dụ.
- Nếu DI container tạo một pool dùng chung, composition root/container thường chịu trách nhiệm đóng pool khi shutdown. Service được inject pool **không nên đóng pool dùng chung sau mỗi request**.
- Nếu một collaborator được inject đã có scope do framework quản lý, service cần dùng theo hợp đồng scope; không giữ tham chiếu sang giai đoạn sống dài hơn.
- Nếu constructor của một lớp chủ sở hữu tài nguyên **buộc phải mở** tài nguyên, nó cần xử lý ngoại lệ và dọn dẹp trường hợp mở dở dang. Đó là quyết định thiết kế riêng, không phải yêu cầu chung của DI.

Ví dụ: inject `DataSource` không có nghĩa constructor phải gọi `getConnection()` để “thử” trước. Lấy một connection nên nằm trong transaction hoặc readiness check có tên rõ ràng, còn đóng connection/pool theo đúng hợp đồng của API được sử dụng.

## 8. Những “kiểm tra đầu vào” thực chất là nghiệp vụ

Một lỗi thiết kế phổ biến là nói “tôi chỉ đang validate” rồi gọi tới các cộng tác viên có I/O ngay trong constructor:

```java
// Phản ví dụ: constructor của service kiểm tra trạng thái bên ngoài.
AccountTransferService(AccountRepository accounts, String accountId) {
    if (!accounts.exists(accountId)) { // Có thể truy vấn DB.
        throw new IllegalArgumentException("Unknown account");
    }
    this.accounts = accounts;
    this.accountId = accountId;
}
```

`accountId` thường là **dữ liệu của một lần chuyển tiền**, không phải cấu hình cố định của một service dùng chung. Kiểm tra tài khoản tồn tại phụ thuộc vào dữ liệu hệ thống tại thời điểm request; ngay cả khi constructor kiểm tra thành công, tài khoản vẫn có thể bị khóa sau đó.

Thiết kế phù hợp hơn:

```java
final class AccountTransferService {
    private final AccountRepository accounts;

    AccountTransferService(AccountRepository accounts) {
        this.accounts = Objects.requireNonNull(accounts);
    }

    void transfer(TransferCommand command) {
        Objects.requireNonNull(command);
        // Thực hiện kiểm tra quyền và trạng thái tài khoản ở đây,
        // trong transaction/chính sách nhất quán phù hợp.
        // Sau đó mới chuyển tiền và ghi nhận kết quả.
    }
}
```

Ví dụ chỉ mô tả cấu trúc: `AccountRepository` và `TransferCommand` là các kiểu do ứng dụng định nghĩa. Thao tác chuyển tiền thực tế cần kiểm tra quyền, tính hợp lệ của số tiền, tính nguyên tử và xử lý giao dịch; việc chuyển code ra khỏi constructor **không tự bảo đảm** tính đúng đắn đó.

Một số câu hỏi để phân loại:

- “`gateway` có phải `null` không?” → Kiểm tra hợp đồng constructor.
- “Chuỗi endpoint có đúng dạng URI không?” → Có thể kiểm tra cục bộ khi tạo config.
- “Endpoint hiện có trả HTTP 200 không?” → Kiểm tra hạ tầng tại thời điểm có chủ đích.
- “Khách hàng còn đủ tiền không?” → Quy tắc nghiệp vụ của lệnh giao dịch, cần kiểm soát tính nhất quán.
- “Có nên tự gửi mail chào mừng khi service được tạo không?” → Đây là hành vi nghiệp vụ, không nên giấu trong constructor.

## 9. Những lưu ý Java dễ bị bỏ qua

### Không gọi phương thức có thể override từ constructor

Constructor của lớp cha có thể chạy **trước** khi trường của lớp con được khởi tạo đầy đủ. Nếu constructor gọi một phương thức có thể override, Java sẽ dispatch tới implementation của lớp con; logic đó có thể nhìn thấy trạng thái chưa sẵn sàng.

```java
class BaseJob {
    BaseJob() {
        run(); // Nguy hiểm: lời gọi có thể chạy code của lớp con.
    }

    void run() {}
}

final class NamedJob extends BaseJob {
    private final String name = "daily";

    @Override
    void run() {
        System.out.println(name); // Có thể in null khi BaseJob() chạy.
    }
}
```

Không nên bắt đầu luồng, đăng ký callback hay phát tán `this` từ constructor trước khi đối tượng khởi tạo xong. Chúng cũng có thể làm phần mã khác nhìn thấy đối tượng chưa hoàn chỉnh. Với tác vụ cần chạy lúc start, dùng lifecycle/điểm khởi động có chủ ý sau khi lắp ghép.

### Đừng biến constructor thành nơi làm việc nặng

Ngay cả phép tính hoàn toàn cục bộ cũng có thể quá đắt: build index lớn, giải nén bộ dữ liệu, biên dịch biểu thức khổng lồ. Khi hiệu năng khởi tạo là một phần quan trọng của hệ thống, hãy cân nhắc precomputation, lazy loading có kiểm soát hoặc bước startup riêng. Tuy nhiên, phép chuẩn hóa nhỏ và tính hash bất biến là hoạt động constructor bình thường.

### Tránh đánh đồng “constructor luôn nhẹ” với “mọi đối tượng luôn sẵn sàng xử lý”

Một client có thể được cấu hình hợp lệ nhưng chưa kết nối. Hợp đồng của lớp cần nói rõ nó sẽ **tự mở kết nối theo yêu cầu**, cần **khởi động trước**, hay có **trạng thái chưa sẵn sàng**. Nếu lớp có `start()` và `close()`, phải quy định hành vi khi gọi hai lần, khi start thất bại, khi nhiều luồng truy cập và khi close đang diễn ra. Đừng thêm lifecycle phức tạp khi factory/session per-call là đủ.

## 10. Cách refactor constructor đang có side effect

Giả sử đang có code tương tự:

```java
final class ReportSender {
    private final ReportGateway gateway;

    ReportSender(String endpoint) {
        gateway = new HttpReportGateway(endpoint);
        gateway.ping();
        gateway.sendDailySummary();
    }
}
```

Các bước refactor có thể tiến hành theo thứ tự:

1. **Xác định bất biến cục bộ:** endpoint bắt buộc, định dạng URI và cấu hình retry. Giữ chúng ở constructor của cấu hình hoặc factory chuyên trách, tránh gọi network để chứng minh hợp lệ.
2. **Xác định collaborator:** `ReportGateway` cung cấp hành vi gửi; chuyển implementation selection và khởi tạo sang composition root rồi truyền qua constructor.
3. **Tách hành vi nghiệp vụ thành phương thức:** `sendDailySummary()` phải được caller yêu cầu, hoặc được scheduler gọi theo lịch; không gắn với mỗi lần tạo service.
4. **Đặt kiểm tra kết nối đúng nơi:** nếu bắt buộc phải ping khi startup, thực hiện ở bước readiness riêng có giới hạn thời gian và cách phản ứng khi lỗi.
5. **Xác định ownership:** nếu `HttpReportGateway` giữ tài nguyên dài hạn, nơi tạo/chủ sở hữu sẽ đóng nó khi shutdown; không để mỗi `ReportSender` tự đóng một client dùng chung.
6. **Kiểm thử bằng fake:** xác minh tạo `ReportSender` không gọi `ping` hoặc `sendDailySummary`, còn thao tác nghiệp vụ gửi đúng một lần khi được gọi.

Hình dạng kết quả trong lớp nghiệp vụ:

```java
final class ReportSender {
    private final ReportGateway gateway;

    ReportSender(ReportGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway);
    }

    void sendDailySummary() {
        gateway.sendDailySummary();
    }
}
```

Phần code này minh họa thiết kế khi `ReportGateway` đã tồn tại. Chỉ dựa vào constructor injection chưa đủ để đảm bảo ứng dụng hoạt động; composition root cần cung cấp implementation phù hợp và chính sách startup phải xét tới tính khả dụng của hạ tầng.

## 11. Bài tập tự kiểm tra

Phân loại các hành động sau thành **A — kiểm tra/gán bất biến tại constructor**, **B — khởi động/kiểm tra hạ tầng có chủ đích**, **C — nghiệp vụ theo lời gọi**, hoặc **D — vòng đời/đóng tài nguyên**.

| Hành động | Lựa chọn |
|---|---|
| `Objects.requireNonNull(clock)` | ? |
| Từ chối `maxConnections <= 0` | ? |
| Gọi `repository.findById(customerId)` để xử lý đơn hiện tại | ? |
| Ping database trước khi đánh dấu ứng dụng ready | ? |
| Gọi `paymentGateway.charge(order)` | ? |
| Đóng session sau khi thực hiện xong một giao dịch | ? |
| Ngắt worker và đóng pool khi ứng dụng shutdown | ? |
| `URI.create(endpoint)` để phát hiện cú pháp không hợp lệ mà không kết nối | ? |

<details>
<summary>Đáp án gợi ý</summary>

Theo thứ tự: **A, A, C, B, C, D, D, A**.

Trường hợp `repository.findById(...)` và `paymentGateway.charge(...)` là tác vụ theo yêu cầu hiện tại; nơi đặt thao tác còn phụ thuộc transaction, quyền truy cập và quy tắc nghiệp vụ. `URI.create(...)` chỉ phân tích cú pháp và không tự thực hiện HTTP request, nên có thể đặt trong bước kiểm tra cấu hình. Đối với API cụ thể, cần xác nhận hàm gọi có làm I/O hay không trước khi phân loại.

</details>

Một câu hỏi nâng cao: nếu hệ thống bắt buộc kết nối tới broker trước khi nhận request, nên thêm `broker.connect()` vào constructor của mọi service hay tạo một thành phần quản lý kết nối, khởi động rõ ràng ở composition root và inject nó vào các service? Phương án thứ hai giúp tập trung chính sách timeout, retry, shutdown và chia sẻ tài nguyên. Tuy vậy, cách thiết kế chính xác còn phụ thuộc broker client, thread safety và hợp đồng connection pooling.

## 12. Ghi nhớ

- **Kiểm tra constructor** nhằm bảo vệ bất biến cục bộ: dependency bắt buộc, cấu hình hợp lệ và trạng thái nhất quán.
- **Kết nối, truy vấn remote và xử lý nghiệp vụ** là những thao tác có thời điểm, lỗi và ownership riêng. Nên biểu diễn bằng phương thức nghiệp vụ, factory hoặc lifecycle có chủ đích.
- **Fail fast** không đồng nghĩa đưa I/O vào constructor. Có thể từ chối cấu hình sai ngay khi tạo, đồng thời kiểm tra hạ tầng ở startup/readiness theo yêu cầu hệ thống.
- **Constructor injection** làm rõ collaborator mà service cần; **composition root** chọn và lắp các implementation; **scope/lifecycle** quyết định tài nguyên được mở, dùng và đóng ở đâu.
- **Kiểm thử Java thuần** có thể chứng minh thời điểm side effect: tạo service không mở kết nối, lệnh nghiệp vụ mới sử dụng fake session và tài nguyên vẫn được đóng khi lỗi.
