# Tiêu chí cần container và trường hợp DI thủ công đã đủ

## 1. Chọn công cụ dựa trên bài toán lắp ghép, không dựa trên tên framework

**Dependency Injection (DI)** là kỹ thuật cung cấp phụ thuộc cho đối tượng sử dụng từ bên ngoài, qua constructor, tham số phương thức hoặc một cơ chế thích hợp khác. **Inversion of Control (IoC)** là ý tưởng rộng hơn về việc chuyển một phần quyền quyết định/điều phối ra khỏi thành phần đang sử dụng. Một **DI container** là công cụ hỗ trợ đăng ký, tạo, kết nối và đôi khi quản lý vòng đời các đối tượng.

Ba khái niệm liên quan nhưng không đồng nhất. **Ứng dụng vẫn có DI khi không dùng Spring, CDI, Guice hay container nào**: một constructor nhận các phụ thuộc đã được tạo ở `main()` là một ví dụ hợp lệ.

~~~java
// Java thuần: constructor injection và composition root.
PaymentGateway gateway = new SandboxPaymentGateway();
ReceiptSender receipts = new ConsoleReceiptSender();
CheckoutService checkout = new CheckoutService(gateway, receipts);
~~~

Đoạn trên chỉ minh họa mối quan hệ; các lớp được định nghĩa ở ứng dụng. Nơi chứa các lệnh khởi tạo và lắp ghép gần điểm khởi động gọi là **composition root**. Nó chịu trách nhiệm chọn hiện thực, cấu hình dependency và xác định ai sở hữu tài nguyên.

Một container có thể giảm công lắp ghép khi hệ thống phức tạp, nhưng đồng thời bổ sung cơ chế đăng ký, cách giải quyết nhiều ứng viên, scope, lifecycle hook và quy tắc framework mà đội ngũ phải hiểu. Vì vậy, câu hỏi đúng là:

> **Việc tự quản lý object graph đang tạo ra chi phí và lỗi thực tế mà một container có thể giảm đáng kể hay chưa?**

Bài này thuộc chương **Bộ chứa DI** của module **DEPENDENCY_INJECTION**. Ta sẽ xây dựng tiêu chí quyết định từ constructor injection, composition root, scope/vòng đời và kiểm thử Java thuần, rồi mới xem container tự động hóa được phần nào.

## 2. Hai cách lắp ghép cùng một object graph

Hình dung một chức năng phát hành biên nhận:

- `ReceiptService` cần `MessageSender`, `AuditLog`, `ReceiptFormatter` và `Clock`.
- `ConsoleSender` là hiện thực của `MessageSender`.
- `FileAuditLog` ghi tệp và cần được đóng khi ứng dụng kết thúc.
- `ReceiptFormatter` và `Clock` cung cấp định dạng và thời gian.

~~~mermaid
flowchart TD
    Root["Composition root hoặc DI container"]
    Service["ReceiptService"]
    Sender["ConsoleSender : MessageSender"]
    Audit["FileAuditLog : AuditLog"]
    Formatter["ReceiptFormatter"]
    Clock["Clock"]

    Root -->|"tạo và lắp ghép"| Service
    Root -->|"tạo"| Sender
    Root -->|"mở tài nguyên"| Audit
    Root -->|"tạo"| Formatter
    Root -->|"chọn"| Clock
    Service --> Sender
    Service --> Audit
    Service --> Formatter
    Service --> Clock
~~~

**Với DI thủ công**, mã ở composition root viết rõ từng bước tạo/ghép. **Với container**, ta cung cấp cách đăng ký, metadata hoặc factory method; container tìm và tạo các nút theo hợp đồng. Trong cả hai cách, `ReceiptService` vẫn có thể giữ **cùng một constructor**.

| Quyết định thiết kế | DI thủ công | DI container |
| --- | --- | --- |
| Service cần những gì | Tham số constructor | Vẫn là tham số constructor/hợp đồng của service |
| Hiện thực nào được chọn | Lệnh `new`/factory/cấu hình ở composition root | Đăng ký thành phần, qualifier, factory method hoặc cấu hình container |
| Thời điểm tạo | Do mã startup/factory quyết định | Do cấu hình khởi tạo và scope của container quyết định |
| Dùng chung hay tạo mới | Code quản lý instance và factory rõ ràng | Scope hoặc provider do container hỗ trợ |
| Tài nguyên được đóng khi nào | `try-with-resources`, `close()`, lifecycle manager | Hook/lifecycle của container nếu được đăng ký đúng |
| Phát hiện cấu hình sai | Kiểm tra và chạy đường build graph của ứng dụng | Container có thể báo thiếu/trùng/cycle khi resolve; tùy cơ chế |
| Kiểm thử service | Truyền fake/stub bằng Java thuần | **Vẫn có thể** truyền fake/stub mà không khởi động container |

Sự khác biệt chủ yếu là **cách thực thi việc lắp ghép**, không phải nhu cầu tách sử dụng phụ thuộc khỏi tạo phụ thuộc.

## 3. Ví dụ chạy được: DI thủ công đủ cho một ứng dụng nhỏ

Một công cụ dòng lệnh phát hành biên nhận chỉ có một cách gửi thông báo và một tài nguyên ghi audit. Đồ thị của nó có vài thành phần, cấu hình ít biến thể, cần đóng file khi xong. Ta có thể quản lý bằng Java thuần một cách minh bạch.

Lưu toàn bộ đoạn sau thành **`ManualDiDecisionDemo.java`** (Java 11 trở lên):

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ManualDiDecisionDemo {

    public interface MessageSender {
        void send(String destination, String text);
    }

    public interface AuditLog {
        void append(String event) throws IOException;
    }

    public static final class ConsoleSender implements MessageSender {
        @Override
        public void send(String destination, String text) {
            System.out.println("TO " + destination + ": " + text);
        }
    }

    public static final class FileAuditLog
            implements AuditLog, AutoCloseable {
        private final BufferedWriter writer;

        public FileAuditLog(Path file) throws IOException {
            this.writer = Files.newBufferedWriter(
                    Objects.requireNonNull(file, "file"),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        }

        @Override
        public void append(String event) throws IOException {
            writer.write(event);
            writer.newLine();
            writer.flush();
        }

        @Override
        public void close() throws IOException {
            writer.close();
        }
    }

    // Thành phần thuần túy, ổn định: dùng lớp cụ thể cũng là DI.
    public static final class ReceiptFormatter {
        public String format(String orderId, Instant issuedAt) {
            return "Biên nhận " + orderId + " lúc " + issuedAt;
        }
    }

    public static final class ReceiptService {
        private final MessageSender sender;
        private final AuditLog audit;
        private final ReceiptFormatter formatter;
        private final Clock clock;

        public ReceiptService(
                MessageSender sender,
                AuditLog audit,
                ReceiptFormatter formatter,
                Clock clock) {
            this.sender = Objects.requireNonNull(sender, "sender");
            this.audit = Objects.requireNonNull(audit, "audit");
            this.formatter = Objects.requireNonNull(formatter, "formatter");
            this.clock = Objects.requireNonNull(clock, "clock");
        }

        public void issue(String orderId, String destination)
                throws IOException {
            if (orderId == null || !orderId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
            if (destination == null || destination.isBlank()) {
                throw new IllegalArgumentException(
                        "destination không được để trống");
            }

            String message = formatter.format(orderId, clock.instant());
            sender.send(destination, message);
            audit.append("RECEIPT_SENT:" + orderId);
        }

        // Service chỉ sử dụng; nó không đóng AuditLog dùng chung.
    }

    // Composition root sở hữu tài nguyên file.
    public static final class ApplicationGraph implements AutoCloseable {
        private final FileAuditLog audit;
        private final ReceiptService receipts;

        private ApplicationGraph(
                FileAuditLog audit, ReceiptService receipts) {
            this.audit = audit;
            this.receipts = receipts;
        }

        public static ApplicationGraph open(Path auditFile)
                throws IOException {
            FileAuditLog audit = new FileAuditLog(auditFile);
            try {
                MessageSender sender = new ConsoleSender();
                ReceiptFormatter formatter = new ReceiptFormatter();
                Clock clock = Clock.systemUTC();
                ReceiptService service = new ReceiptService(
                        sender, audit, formatter, clock);
                return new ApplicationGraph(audit, service);
            } catch (RuntimeException | Error failure) {
                // Đã mở file nhưng chưa chuyển giao graph: phải đóng.
                try {
                    audit.close();
                } catch (IOException closeFailure) {
                    failure.addSuppressed(closeFailure);
                }
                throw failure;
            }
        }

        public ReceiptService receipts() {
            return receipts;
        }

        @Override
        public void close() throws IOException {
            audit.close();
        }
    }

    public static void main(String[] args) throws IOException {
        try (ApplicationGraph app =
                ApplicationGraph.open(Path.of("receipt-audit.log"))) {
            app.receipts().issue("ORDER-001", "an@example.com");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ManualDiDecisionDemo.java
java ManualDiDecisionDemo
~~~

Kết quả trên console có dạng:

~~~text
TO an@example.com: Biên nhận ORDER-001 lúc <ISO-8601 timestamp>
~~~

Thời điểm thực tế phụ thuộc lúc chạy chương trình nên **không cố định** như dòng minh họa. Tệp `receipt-audit.log` được tạo hoặc nối thêm một dòng `RECEIPT_SENT:ORDER-001`. Ví dụ chỉ minh họa lắp ghép và vòng đời; **gửi thông báo thành công nhưng ghi audit thất bại vẫn là tình huống có tác dụng phụ một phần**, cần chính sách nghiệp vụ riêng trong hệ thống thật.

Ở đây, composition root kiểm soát trọn vẹn:

1. **Chọn hiện thực** gửi thông báo.
2. **Mở tài nguyên** audit và giữ quyền sở hữu.
3. **Lắp ghép** `ReceiptService` bằng constructor injection.
4. **Trả về graph đã hoàn chỉnh**; nếu lỗi trong lúc dựng graph sau khi mở tệp, cố đóng tệp.
5. **Đóng tài nguyên** sau khi xử lý xong bằng `try-with-resources`.

Không có cơ chế kỹ thuật nào ở đây bắt buộc phải dùng container. Đối với một ứng dụng tương đối nhỏ và ít biến thể, đoạn lắp ghép này thường dễ đọc và đủ để vận hành.

## 4. Kiểm thử Java thuần cho thấy có DI không cần container

Một lý do thường được nêu để đưa framework DI vào dự án là “để test được”. Nhưng test cho `ReceiptService` chỉ cần cung cấp các dependency qua constructor. Ta không cần khởi động application context, quét component hay dùng annotation.

Tạo **`ManualDiDecisionDemoTest.java`** bên cạnh chương trình:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class ManualDiDecisionDemoTest {

    static final class RecordingSender
            implements ManualDiDecisionDemo.MessageSender {
        int calls;
        String recipient;
        String text;

        @Override
        public void send(String destination, String message) {
            calls++;
            recipient = destination;
            text = message;
        }
    }

    static final class RecordingAudit
            implements ManualDiDecisionDemo.AuditLog {
        final List<String> events = new ArrayList<>();

        @Override
        public void append(String event) {
            events.add(event);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        RecordingSender sender = new RecordingSender();
        RecordingAudit audit = new RecordingAudit();

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);

        ManualDiDecisionDemo.ReceiptService service =
                new ManualDiDecisionDemo.ReceiptService(
                        sender,
                        audit,
                        new ManualDiDecisionDemo.ReceiptFormatter(),
                        fixedClock);

        service.issue("ORDER-123", "an@example.com");

        check(sender.calls == 1, "Phải gửi một lần");
        check("an@example.com".equals(sender.recipient),
                "Sai người nhận");
        check(sender.text.contains("ORDER-123"), "Thiếu mã đơn");
        check(sender.text.contains("2026-01-01T00:00:00Z"),
                "Thời gian không được cố định theo clock giả");
        check(audit.events.equals(List.of("RECEIPT_SENT:ORDER-123")),
                "Sai sự kiện audit");

        try {
            service.issue("invalid id", "an@example.com");
            throw new AssertionError("Phải từ chối orderId sai");
        } catch (IllegalArgumentException expected) {
            check(sender.calls == 1, "Không gửi với dữ liệu sai");
            check(audit.events.size() == 1, "Không audit dữ liệu sai");
        }

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac ManualDiDecisionDemo.java ManualDiDecisionDemoTest.java
java ManualDiDecisionDemoTest
~~~

Hai fake ghi nhận lời gọi, còn `Clock.fixed(...)` biến thời gian thành dữ liệu tất định. Kiểm thử chỉ dùng các đối tượng cần thiết, vì vậy không bị ràng buộc vào vòng đời container hoặc tài nguyên I/O.

**Diễn giải đúng:** container có thể giúp tạo môi trường **integration test** gần với cấu hình sản phẩm, nhưng **unit test của service không nhất thiết phải khởi động container**. Tính dễ kiểm thử đến từ việc khai báo và cung cấp phụ thuộc rõ ràng.

## 5. Container bổ sung khả năng gì khi đồ thị lớn lên?

DI container giúp giảm công tổ chức object graph bằng một số cơ chế, tùy sản phẩm và cấu hình:

| Khả năng | Tác dụng khi phức tạp tăng | Điều vẫn phải tự quyết định |
| --- | --- | --- |
| Đăng ký bean/component và resolve theo type | Không cần viết thủ công mọi lệnh nối đối tượng | Hợp đồng nào nên được tiêm và ranh giới module ở đâu |
| Qualifier, tên đăng ký và ưu tiên | Chọn một trong nhiều implementation phù hợp | Semantics của lựa chọn, khi nào cần fail fast |
| Scope như singleton, request, prototype/transient | Tái sử dụng hoặc tạo mới theo chính sách | Có an toàn luồng không, có captive dependency không |
| Factory method, provider và lazy resolution | Tạo muộn, cấp theo yêu cầu và quản lý một số trường hợp vòng đời | Trạng thái sản phẩm, quyền sở hữu, hành vi khi lỗi |
| Hook khởi tạo và kết thúc | Gọi callback/`close()` cho bean được quản lý | Shutdown thứ tự nào, request còn đang chạy không |
| Cấu hình theo profile/môi trường | Chọn adapter theo cách triển khai | Cấu hình nào được hỗ trợ, kiểm tra tính đầy đủ ra sao |
| Chẩn đoán thiếu bean, vòng phụ thuộc | Một số lỗi lắp ghép xuất hiện sớm ở startup | Lỗi không nằm trong graph, lỗi runtime và lỗi logic vẫn phải xử lý |
| Tích hợp với framework web, persistence, messaging | Đồng bộ vòng đời thành phần với request, transaction hoặc job | Transaction boundary, retry, authorization và tính nhất quán |

**Không có cơ chế duy nhất áp dụng giống nhau cho mọi container.** Spring, CDI, Guice và các container khác có phạm vi chức năng, quy tắc mặc định và cách cấu hình khác nhau. Không nên giả định rằng tính năng của một framework sẽ tồn tại trong mọi framework DI.

Một container thường mang lại giá trị lớn hơn khi đội ngũ đang phải **tự xây các quy tắc chọn thành phần, scope, factory, lifecycle và cấu hình** lặp đi lặp lại ở nhiều module. Khi ấy container giúp chuẩn hóa phần cơ sở hạ tầng thay vì mỗi nhóm viết một bộ container nhỏ riêng.

## 6. Tiêu chí chọn container: đánh giá theo chi phí duy trì thực tế

Đừng quyết định theo một ngưỡng cứng như “từ 20 class trở lên thì phải dùng Spring”. Một đồ thị có hàng chục node nhưng ổn định, ít scope và ít biến thể có thể dễ bảo trì hơn một đồ thị chỉ vài node nhưng phụ thuộc vào hàng loạt request-scoped resource.

Bảng đánh giá sau dùng các **dấu hiệu thực tế**:

| Tiêu chí | DI thủ công thường đã đủ khi... | Container đáng cân nhắc khi... |
| --- | --- | --- |
| **Độ phức tạp object graph** | Các bước lắp ghép tập trung, ngắn và dễ đọc | Nhiều graph, nhiều nhánh cấu hình và thay đổi liên tục |
| **Tốc độ thay đổi hiện thực** | Ít adapter; thay đổi tại composition root dễ kiểm soát | Nhiều biến thể theo môi trường, tenant, tính năng hoặc plugin |
| **Scope và lifecycle** | Chủ yếu application-scope hoặc các task có `try-with-resources` rõ | Request/session/job scope đa tầng cần giải quyết nhất quán |
| **Khởi tạo tài nguyên** | Tài nguyên ít, ownership rõ và cleanup đơn giản | Nhiều resource, thứ tự init/shutdown và callback phức tạp |
| **Tổ chức đội ngũ/module** | Một nhóm có thể nhìn và kiểm soát việc lắp ghép | Nhiều nhóm/module đăng ký component độc lập, cần quy ước chung |
| **Framework đang dùng** | Ứng dụng Java thuần hoặc thư viện độc lập | Framework web/persistence đã cung cấp container và lifecycle tích hợp |
| **Độ quan sát lỗi cấu hình** | Có test lắp ghép và lỗi dễ xác định | Cần validation/diagnostics nhất quán qua nhiều cấu hình triển khai |
| **Chi phí học và vận hành** | Đội ngũ nắm vững constructor/factory, ít phụ thuộc công cụ | Lợi ích tự động hóa lớn hơn chi phí annotation, metadata, debug |
| **Yêu cầu khởi động** | Muốn startup tối giản, footprint nhỏ, có graph tĩnh | Chấp nhận chi phí khởi tạo container để đổi lấy quản trị phức tạp |

Đây là **ma trận gợi ý**, không phải bộ điều kiện để tính điểm máy móc. Hai hoặc ba dấu hiệu quan trọng cùng xuất hiện có thể là lý do tốt để thử container, nhưng cần kiểm chứng bằng cấu hình và bài toán cụ thể.

### Tín hiệu nên ưu tiên điều tra trước

- Composition root phình to vì phải tự kiểm tra **hàng loạt biến thể**, không chỉ vì có nhiều lệnh `new`.
- Mỗi module tự viết một registry/service locator, cơ chế lựa chọn và lifecycle riêng.
- Lỗi thiếu binding, scope mismatch hoặc cleanup lặp lại qua nhiều môi trường.
- Phần lớn code mới là wiring mà không bổ sung quy tắc nghiệp vụ.
- Một framework hiện hữu đã có container chính thức, nhưng nhóm đang cố duy trì hệ lắp ghép tay song song mà không có lợi ích rõ.

Ngược lại, nếu phần wiring chiếm một tệp ngắn, đọc một lượt là hiểu, unit test không cần context và resource dễ đóng, **chi phí chuyển sang container có thể lớn hơn lợi ích ngay lúc này**.

## 7. Ba tình huống đối chiếu

### Tình huống A — Công cụ dòng lệnh một lần chạy

Một tiện ích đọc CSV, áp quy tắc chuẩn hóa, ghi kết quả và kết thúc. Mỗi job mở nguồn và đích rồi đóng bằng `try-with-resources`. Không có request scope, ít cách cấu hình, những thành phần cần dùng được biết ngay tại `main()`.

**Quyết định thường hợp lý: DI thủ công.** Constructor injection cho các policy, factory cho stream nếu cần, composition root nhỏ và đường cleanup rõ ràng. Thêm container có thể tăng cấu hình, thời gian khởi động và lượng khái niệm phải học mà không giảm nhiều mã thật.

### Tình huống B — Dịch vụ web với nhiều adapter và scope

Ứng dụng có HTTP request, hàng đợi sự kiện, repository, cache, nhiều cổng thanh toán theo môi trường, transaction theo request, client dùng chung và shutdown phối hợp. Một số component phụ thuộc vào profile hoặc feature flag; nhiều module được phát triển độc lập.

**Quyết định: container đáng để đánh giá.** Nó có thể chuẩn hóa lắp ghép, phân giải phụ thuộc, scope và lifecycle. Tuy nhiên, phải định nghĩa ranh giới transaction, chọn adapter, phân biệt singleton với request state và kiểm tra shutdown thực tế. Nếu ứng dụng dùng framework web đã tích hợp container, tận dụng cơ chế ấy thường giúp tránh tạo một lifecycle framework thứ hai.

### Tình huống C — Thư viện Java được dùng trong nhiều môi trường

Một thư viện tính giá hoặc xác thực nghiệp vụ chỉ cần vài interface và class, được sử dụng trong ứng dụng CLI, dịch vụ Spring hoặc một hệ thống khác. Thư viện không tự sở hữu HTTP server hay request lifecycle.

**Quyết định thường hợp lý: giữ core bằng constructor injection Java thuần**, để ứng dụng dùng thư viện chọn cách lắp ghép. Một module tích hợp riêng có thể khai báo bean/container binding nếu cần. Nhờ vậy thư viện vẫn dùng được ở môi trường không có framework DI.

Ba ví dụ cho thấy **loại ứng dụng và trách nhiệm vòng đời** thường quan trọng hơn số lượng class.

## 8. Cái giá của container cũng là một phần của quyết định

Một container giải quyết một nhóm bài toán nhưng có chi phí cần quản lý:

**Độ phức tạp cấu hình.** Có thể có nhiều cách đăng ký cùng một type: annotation scan, factory method, conditional binding, profile và override cho test. Nếu không có quy ước rõ, lựa chọn implementation trở nên khó nhìn hơn lệnh `new` tường minh.

**Lỗi chuyển thời điểm.** Container thường có thể phát hiện nhiều lỗi graph khi khởi động, nhưng cấu hình lazy hoặc provider có thể dời lỗi đến lần dùng đầu tiên. Không nên đồng nhất “context khởi động thành công” với “mọi tính năng và mọi hệ thống ngoài luôn sẵn sàng”.

**Khả năng quan sát object graph.** Khi wiring được suy ra từ annotation/metadata, người review phải biết cách tra dependency, qualifier và scope. Nên tận dụng công cụ chẩn đoán hoặc test lắp ghép có chủ đích.

**Hiệu suất và tài nguyên.** Việc quét, phản chiếu (reflection), proxy, khởi tạo bean và metadata có thể tác động footprint hoặc startup, tùy cách dùng. Mức độ ảnh hưởng phải **đo trong ứng dụng thực tế**, không suy ra chỉ từ việc có container.

**Phụ thuộc framework.** Nếu mã nghiệp vụ cần trực tiếp một `ApplicationContext` hoặc API container để chạy, phần core khó sử dụng/kiểm thử độc lập hơn. Tốt hơn là giới hạn API container ở nơi lắp ghép, adapter hoặc thành phần tích hợp thật sự cần nó.

**Quy tắc vòng đời khó thấy.** Một singleton giữ session request-scoped, task bất đồng bộ truy cập request proxy sau khi scope kết thúc hoặc bean không được đóng đúng cách vẫn có thể xảy ra. Container không tự suy ra ownership và ý nghĩa nghiệp vụ cho mọi resource.

Chọn container vì nó **giảm tổng chi phí vận hành và bảo trì** của graph, chứ không vì mong muốn loại bỏ hết lệnh `new` khỏi chương trình.

## 9. Scope và vòng đời: điểm dễ đưa ra quyết định sai nhất

Phân biệt ba loại quan hệ:

| Consumer | Dependency | Có thể hợp lý? | Điều kiện |
| --- | --- | --- | --- |
| Singleton/app-scoped service | Shared client/pool app-scoped | Có | Client đủ an toàn với concurrency, đóng khi app ngừng |
| Request-scoped handler | Shared client app-scoped | Có | Handler mượn client và không đóng nó khi kết thúc request |
| Singleton service giữ **instance thật** của request context | Request-scoped state | Thường sai | Context có thể hết hiệu lực trong khi singleton vẫn dùng |
| Singleton service giữ factory/provider | Tạo hoặc phân giải dependency theo tác vụ/scope | Có thể | Không cache instance ngắn hạn; resolve trong scope hợp lệ |
| Task chạy nền giữ object thuộc HTTP request | Request-scoped context | Rủi ro | Phải chuyển dữ liệu phù hợp hoặc tạo scope công việc riêng |

Ví dụ nguy hiểm:

~~~java
// Phác họa sai scope, không phải file độc lập.
final class ReportService {
    private final RequestContext request; // Request 1 bị giữ lâu.

    ReportService(RequestContext request) {
        this.request = request;
    }
}
~~~

Chuyển sang container mà giữ nguyên ý tưởng này không mặc nhiên làm nó an toàn. Một số container sẽ phát hiện scope mismatch, một số dùng proxy hoặc provider, một số để lỗi xuất hiện khi sử dụng. **Hành vi cụ thể phụ thuộc cấu hình framework.**

Với DI thủ công, có thể truyền context qua tham số phương thức:

~~~java
void generateReport(RequestContext request, String reportId) {
    // Dùng request trong lần gọi; không lưu vào field sống lâu.
}
~~~

Khi tạo đối tượng gắn với request, request boundary có thể dùng factory:

~~~java
try (ReportSession session = sessionFactory.open(requestId)) {
    session.generateReport(reportId);
}
~~~

Hai đoạn chỉ minh họa API và giả định các type được ứng dụng định nghĩa. Điểm chính là **phạm vi sử dụng và quyền đóng phải được thiết kế trước**, bất kể container hay manual DI.

### Shutdown không biến mất khi dùng container

Nếu ứng dụng đang nhận request hoặc xử lý job, việc đóng pool/client quá sớm vẫn làm tác vụ hỏng. Cần dừng nhận việc mới, đợi hoặc hủy tác vụ theo chính sách, rồi đóng resource theo thứ tự phụ thuộc. Một callback như `@PreDestroy` hoặc một phương thức `close()` được container gọi chỉ là **điểm thực thi** của chính sách vòng đời ấy.

## 10. Khi chuyển sang container, nên giữ nguyên ranh giới nghiệp vụ

Giả sử ứng dụng sau này sử dụng Spring. `ReceiptService` có thể giữ nguyên constructor nhận `MessageSender`, `AuditLog`, `ReceiptFormatter`, `Clock`. Ta chuyển cách lắp ghép ở composition root thành cấu hình bean.

Ví dụ dưới đây là **mã minh họa tích hợp Spring**, yêu cầu các thư viện và cấu hình ứng dụng Spring tương ứng; không phải phần của chương trình Java thuần đã chạy ở trên:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ReceiptWiring {
    @Bean
    ManualDiDecisionDemo.MessageSender messageSender() {
        return new ManualDiDecisionDemo.ConsoleSender();
    }

    @Bean
    ManualDiDecisionDemo.ReceiptFormatter receiptFormatter() {
        return new ManualDiDecisionDemo.ReceiptFormatter();
    }

    @Bean
    Clock receiptClock() {
        return Clock.systemUTC();
    }

    @Bean(destroyMethod = "close")
    ManualDiDecisionDemo.FileAuditLog auditLog() throws IOException {
        return new ManualDiDecisionDemo.FileAuditLog(
                Path.of("receipt-audit.log"));
    }

    @Bean
    ManualDiDecisionDemo.ReceiptService receiptService(
            ManualDiDecisionDemo.MessageSender sender,
            ManualDiDecisionDemo.AuditLog audit,
            ManualDiDecisionDemo.ReceiptFormatter formatter,
            Clock clock) {
        return new ManualDiDecisionDemo.ReceiptService(
                sender, audit, formatter, clock);
    }
}
~~~

Ở cấu hình này, Spring có thể tạo các bean, resolve phụ thuộc theo type và sử dụng phương thức close được cấu hình khi application context đóng. Với nhiều bean cùng type, cần chỉ rõ lựa chọn phù hợp, ví dụ qualifier. Cách tạo application context, scope và shutdown cụ thể phải được thiết lập trong ứng dụng Spring thực tế.

**Điểm cần giữ:** `ReceiptService` hoàn toàn không import Spring, không gọi `getBean()` và không biết cách khởi tạo `FileAuditLog`. Chuyển công cụ lắp ghép **không buộc phải thay đổi lõi nghiệp vụ**.

### Đừng dùng container làm service locator tổng quát

Ví dụ nên cân nhắc lại:

~~~java
// Phác họa cách che giấu dependency.
final class ReceiptService {
    private final ApplicationContext context;

    ReceiptService(ApplicationContext context) {
        this.context = context;
    }

    void issue() {
        MessageSender sender = context.getBean(MessageSender.class);
        // ...
    }
}
~~~

Các type trong phác họa cần import/cấu hình framework tương ứng. Đoạn này làm mất tính rõ ràng của dependency ở constructor. Service phụ thuộc vào container thay vì hợp đồng thật. Nếu cần chọn sender động theo dữ liệu runtime, nên tiêm một **factory, registry hoặc router chuyên biệt** có API biểu diễn quyết định nghiệp vụ.

## 11. Lộ trình chuyển đổi khi DI thủ công bắt đầu quá tải

Không cần chuyển toàn bộ dự án trong một lần. Một lộ trình giảm rủi ro:

1. **Vẽ lại object graph đang có.** Xác định composition root, hợp đồng, adapter, singleton, instance theo request/job, factory và tài nguyên cần đóng.
2. **Giữ constructor rõ ràng.** Đảm bảo service nhận dependency qua constructor hoặc tham số phương thức; tránh tạo adapter trong logic nghiệp vụ và tránh global service locator.
3. **Chọn phần wiring lặp lại để chuyển trước.** Ví dụ đăng ký repository, client, policy và lựa chọn adapter theo môi trường.
4. **Khai báo scope và owner ngay từ đầu.** Đặc biệt kiểm tra singleton có giữ request state, transaction hoặc connection mượn không.
5. **Dùng container cho graph, giữ test nghiệp vụ thuần Java.** Viết một số integration test khởi động context và xác minh wiring; unit test vẫn trực tiếp tạo service và fake.
6. **Kiểm tra lỗi cấu hình ở startup.** Thử thiếu bean, nhiều ứng viên, vòng phụ thuộc, cấu hình profile khác nhau và lỗi khi tạo resource.
7. **Kiểm tra vòng đời thực tế.** Đóng context trong test/ứng dụng và xác nhận resource được đóng; kiểm tra shutdown khi còn tác vụ.
8. **Xóa đường wiring cũ đã bị thay thế.** Tránh duy trì hai cơ chế chọn component hoặc hai nơi sở hữu cùng một tài nguyên.

~~~mermaid
flowchart LR
    A["Manual composition root rõ ràng"] --> B["Đo chi phí wiring và scope"]
    B --> C{"Container đem lại lợi ích đủ lớn?"}
    C -->|"Chưa"| D["Giữ manual DI, cải thiện factory và kiểm thử"]
    C -->|"Có"| E["Đăng ký graph trong container"]
    E --> F["Kiểm tra qualifier/scope/lifecycle"]
    F --> G["Giữ constructor và unit test thuần Java"]
~~~

Lưu ý: không nhất thiết loại bỏ mọi `new` sau khi chọn container. Tạo value object, collection, command, đối tượng tạm và một số factory product trong nghiệp vụ có thể vẫn đúng. Mục tiêu là **đặt quyết định về phụ thuộc và vòng đời ở nơi có trách nhiệm thích hợp**.

## 12. Phép thử lựa chọn bằng tình huống thực tế

Khi cân nhắc container cho một dự án, hãy trả lời theo **bằng chứng từ codebase**:

| Câu hỏi | Dấu hiệu nghiêng về DI thủ công | Dấu hiệu nghiêng về container |
| --- | --- | --- |
| Đồ thị có dễ dựng lại tại một điểm? | Có một hoặc vài composition root ngắn, rõ | Nhiều module cần tự đăng ký và liên kết graph |
| Một thành phần có nhiều cách tạo theo môi trường? | Vài nhánh cấu hình đơn giản | Nhiều điều kiện, qualifier, profile lặp lại |
| Scope khó ở đâu? | Task rõ điểm mở/đóng, chủ yếu tuần tự | Request/session/job scope giao nhau và phải được quản lý thống nhất |
| Có phải triển khai cơ chế registry tự chế? | Không hoặc chỉ registry chuyên biệt nhỏ | Đang xây dần container/service locator tự chế |
| Unit test có phụ thuộc vào công cụ wiring? | Constructor injection hoạt động trực tiếp | Cần nhiều integration test của graph phức tạp; container có diagnostics hữu ích |
| Chi phí chuyển đổi là gì? | Mang thêm thư viện và cấu hình lớn so với ứng dụng | Framework đã có sẵn container và nhóm vận hành nắm rõ |
| Khi lỗi production, có dò được thành phần đã chọn? | Wiring tường minh, dễ trace | Container có công cụ xem graph, scope và nguồn bean hiệu quả |

Một cách kiểm tra có thể áp dụng là **thử chuyển một use case đại diện** sang container trong nhánh thử nghiệm, rồi so sánh: số dòng cấu hình khó hiểu, thời gian debug khi sai binding, mức độ rõ scope/ownership, thời gian khởi động và khả năng viết unit test. Không cần đề xuất chuyển đổi toàn bộ chỉ vì một ví dụ “ít dòng code hơn”.

## 13. Những ngộ nhận thường gặp

| Ngộ nhận | Điều chính xác hơn |
| --- | --- |
| “DI nghĩa là phải dùng Spring hoặc CDI” | Constructor injection bằng Java thuần vẫn là DI |
| “Dùng container thì khỏi cần composition root” | Vẫn có nơi quyết định cấu hình, đăng ký và khởi động graph; hình thức thể hiện thay đổi |
| “Container tự động làm hệ thống ít coupling” | Coupling phụ thuộc ranh giới abstraction và kiến trúc, không chỉ vào cách tạo bean |
| “Càng nhiều class càng phải dùng container” | Độ phức tạp scope, biến thể, ownership và thay đổi quan trọng hơn số lượng class |
| “Container sửa được circular dependency” | Một số cơ chế có thể trì hoãn resolve, nhưng chu trình trách nhiệm vẫn cần thiết kế lại |
| “Một bean singleton chắc chắn thread-safe” | Scope chỉ mô tả chia sẻ instance; thread safety cần thiết kế riêng |
| “Đã có lifecycle callback nên không bao giờ rò rỉ” | Phải khai báo đúng owner, scope và shutdown; các resource không do container quản lý vẫn phải được đóng |
| “Có container thì unit test phải boot context” | Service constructor injection vẫn có thể test bằng fake Java thuần |
| “Có interface thì wiring sẽ tự đúng” | Thiếu/trùng binding, qualifier và cấu hình vẫn có thể sai |
| “Tạo lazy luôn làm startup và lỗi tốt hơn” | Lazy có thể dời lỗi sang request đầu tiên và tăng độ trễ lần đầu |

## 14. Bài tập áp dụng tiêu chí quyết định

**Bài tập 1 — Đọc composition root.** Một công cụ xử lý CSV có `CsvReader`, `Normalizer`, `Validator`, `CsvWriter` và `JobRunner`. Tất cả được tạo tại `main()`, dùng một lần rồi đóng. Hãy vẽ object graph, chỉ ra thứ tự xây dựng/đóng và giải thích vì sao DI thủ công có thể đủ.

**Bài tập 2 — Phần nào bắt đầu phức tạp?** Dịch vụ báo cáo có hai loại repository, ba kênh xuất, nhiều profile cấu hình, một client dùng chung và transaction theo request. Hãy đánh giá từng tiêu chí ở mục 6. Phần nào có thể giải quyết bằng factory/registry chuyên biệt? Phần nào hợp lý khi giao cho container quản lý?

**Bài tập 3 — Kiểm thử không context.** Mở rộng `ReceiptService` thêm `ReceiptPolicy` giới hạn số tiền và thời gian. Tiêm policy qua constructor; dùng `Clock.fixed` và fake sender/audit để viết một test hoàn toàn không cần Spring.

**Bài tập 4 — Scope mismatch.** Một singleton `InvoiceService` giữ một `RequestContext` thực. Viết hai request có danh tính khác nhau để làm lộ lỗi. Sửa bằng method injection hoặc factory, rồi mô tả container có thể giúp **quản lý** request scope ra sao nhưng không thay thế quyết định không giữ state sai vòng đời.

**Bài tập 5 — Migration.** Từ `ApplicationGraph` trong ví dụ, phác thảo cấu hình bean cho từng nút. Chỉ ra bean cần hook đóng tài nguyên, các điểm cần qualifier nếu có thêm sender thứ hai, và test integration cần có để phát hiện cấu hình thiếu/trùng.

**Bài tập 6 — Quyết định có bằng chứng.** Với một dự án bạn đang học hoặc xây dựng, liệt kê những lỗi wiring/lifecycle đã gặp thật và ước lượng phần chi phí do manual DI gây ra. Nếu chưa có lỗi, hãy chọn một phần graph biến động nhiều nhất để mô phỏng việc thêm implementation, thay scope và chạy test. Ghi nhận phần nào container đơn giản hóa, phần nào vẫn phải tự thiết kế.

Ba câu hỏi kiểm tra cuối bài là: **(1) Việc lắp ghép thủ công hiện có còn dễ nhìn, dễ sửa và dễ kiểm thử không? (2) Scope, cấu hình và lifecycle có tạo ra độ phức tạp lặp lại mà container giải quyết tốt hơn không? (3) Nếu dùng container, lớp nghiệp vụ có còn nhận dependency rõ ràng và hoạt động độc lập với framework không?** Trả lời được ba câu này giúp chọn DI thủ công hay DI container theo nhu cầu thực tế thay vì theo thói quen.
