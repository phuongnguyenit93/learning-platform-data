# Tạo điểm tách phụ thuộc để cải thiện khả năng kiểm thử

> **Chương:** Mã hiện hữu  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **điểm tách phụ thuộc (test seam)** là vị trí cho phép thay đổi hoặc kiểm soát một phụ thuộc trong lúc kiểm thử mà không phải sửa logic nghiệp vụ đang được kiểm tra.
2. Nhận diện các phụ thuộc khiến mã hiện hữu khó kiểm thử: database, mạng, filesystem, đồng hồ hệ thống, số ngẫu nhiên, biến toàn cục, lời gọi static, singleton và khởi tạo đối tượng trực tiếp.
3. Phân biệt **logic cần kiểm tra** với **hạ tầng cung cấp dữ liệu hoặc tác dụng phụ**, từ đó đặt ranh giới ở nơi có ý nghĩa.
4. Bổ sung seam từng bước vào mã Java cũ bằng constructor injection, interface/port, adapter, tham số thời gian hoặc hàm được truyền vào.
5. Viết characterization test để ghi nhận hành vi hiện tại trước khi tách phụ thuộc, đồng thời phân biệt hành vi cần giữ với defect đã biết.
6. Dùng fake, stub hoặc mock phù hợp để kiểm tra kết quả, lỗi và tương tác quan trọng mà không biến test thành bản sao của implementation.
7. Kết hợp unit test với integration/contract test để kiểm tra adapter và môi trường thật ở đúng ranh giới.
8. Tránh tạo abstraction quá sớm, test seam quá rộng hoặc thiết kế chỉ để mock; chọn bước cải tiến nhỏ, có thể kiểm chứng và phù hợp với rủi ro.

## 1. Vì sao mã hiện hữu thường khó kiểm thử?

Một lớp trong hệ thống cũ có thể vừa tính toán nghiệp vụ, vừa mở kết nối database, đọc giờ hệ thống, ghi file và gửi email:

~~~java
final class MonthlyStatementJob {
    void run(long customerId) throws Exception {
        var connection = DriverManager.getConnection(
                "jdbc:postgresql://localhost:5432/shop",
                "app", "secret");

        var statement = connection.prepareStatement(
                "select balance from customer_account where id = ?");
        statement.setLong(1, customerId);

        var result = statement.executeQuery();
        if (!result.next()) {
            throw new IllegalArgumentException("Customer not found");
        }

        long balanceVnd = result.getLong("balance");
        long generatedAt = System.currentTimeMillis();

        String content = "Balance: " + balanceVnd
                + ", generatedAt: " + generatedAt;

        Files.writeString(
                Path.of("statements", customerId + ".txt"),
                content);

        new SmtpClient().send(
                "customer@example.test",
                "Monthly statement",
                content);
    }
}
~~~

Đây là ví dụ rút gọn để minh họa phụ thuộc bị tạo trực tiếp; thông tin kết nối chỉ là dữ liệu giả trong ví dụ. Ứng dụng thật phải lấy cấu hình và bí mật từ cơ chế quản lý cấu hình an toàn, đồng thời đóng tài nguyên JDBC đúng cách, chẳng hạn bằng try-with-resources. Khi muốn kiểm tra quy tắc tạo sao kê, test phải đối mặt với nhiều việc ngoài logic:

- Database phải chạy và có dữ liệu đúng.
- Kết nối, credential và schema phải được cấu hình.
- Thời điểm tạo nội dung thay đổi theo đồng hồ của máy.
- File được ghi ra filesystem thật.
- Email có thể bị gửi thật hoặc cần SMTP server giả.
- Test có thể để lại dữ liệu hoặc tác dụng phụ sau khi chạy.

Nếu chỉ muốn kiểm tra rằng số dư 250.000 VND được đưa vào nội dung sao kê, việc khởi động cả database, filesystem và SMTP là quá nhiều phụ thuộc. Test dễ chậm, flaky, khó chẩn đoán và khó chạy độc lập.

Vấn đề nằm ở chỗ **logic nghiệp vụ không có ranh giới để nhận dữ liệu và điều khiển tác dụng phụ**. Ta cần một nơi có thể thay database bằng nguồn dữ liệu giả, thay đồng hồ thật bằng thời điểm cố định và thay SMTP bằng bộ ghi nhận email trong test.

Nơi cho phép làm việc đó là **test seam**.

## 2. Test seam là gì?

Một test seam là điểm trong cấu trúc hoặc luồng chạy mà tại đó có thể thay thế cách một phụ thuộc được cung cấp hoặc cách một hành vi được thực hiện, mà không phải viết lại logic đang cần kiểm tra.

Ví dụ:

- Thay repository truy vấn PostgreSQL bằng repository trong bộ nhớ.
- Truyền một `Clock` cố định thay cho `Instant.now()` hoặc `LocalDate.now()`.
- Thay bộ gửi email bằng fake chỉ ghi lại người nhận và nội dung.
- Truyền một hàm đọc file thay cho việc gọi filesystem trực tiếp.
- Thay HTTP client thật bằng adapter test trả response xác định.
- Cấp một nguồn số ngẫu nhiên có seed cố định cho thuật toán cần lặp lại.

### Seam không nhất thiết là interface

Một điểm tách có thể được tạo bằng:

- Interface và dependency injection.
- Constructor nhận object hoặc interface.
- Tham số hàm nhận một giá trị hoặc callback.
- Factory/provider được truyền từ bên ngoài.
- Adapter bao quanh API static hoặc thư viện bên thứ ba.
- Ranh giới tiến trình, cổng HTTP hoặc cơ sở dữ liệu trong integration test.

Không phải cứ thêm interface là có test seam tốt. Nếu interface không nằm giữa logic cần kiểm tra và phụ thuộc cần thay thế, nó chỉ thêm một tầng chuyển tiếp.

### Phân biệt ba khái niệm

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Dependency** | Thành phần mà logic dựa vào | Repository, Clock, EmailSender |
| **Seam** | Điểm cho phép thay cách cung cấp hoặc thực hiện dependency | Constructor nhận EmailSender |
| **Test double** | Thành phần thay thế được dùng trong test | FakeEmailSender lưu danh sách email |

Dependency là thứ được sử dụng; seam là vị trí cho phép thay nó; test double là một cách tận dụng seam trong kiểm thử.

## 3. Tách logic khỏi tác dụng phụ

Trước khi sửa mã, hãy xác định phần nào là quyết định nghiệp vụ và phần nào là tương tác với thế giới bên ngoài.

Với ví dụ sao kê:

| Phần việc | Loại | Cách kiểm tra phù hợp |
| --- | --- | --- |
| Chọn số dư cần đưa vào sao kê | Logic ứng dụng | Unit/component test |
| Quyết định định dạng thời gian | Logic có quy tắc | Unit test với Clock cố định |
| Truy vấn số dư PostgreSQL | Hạ tầng | Repository integration test |
| Ghi file sao kê | Tác dụng phụ filesystem | Test adapter trên thư mục tạm |
| Gửi email | Tác dụng phụ bên ngoài | Fake ở unit test; contract/integration test cho adapter |
| Chạy cả job theo lịch | Điều phối | Component test hoặc test tích hợp theo phạm vi |

Tách không có nghĩa mọi thao tác phải thành một interface. Mục tiêu là **logic có thể được kiểm tra mà không cần thực hiện các tác dụng phụ không liên quan**.

Một nguyên tắc thực tế: đặt seam tại nơi có thay đổi về công nghệ, môi trường, thời gian, dữ liệu hoặc tác dụng phụ; giữ các phép tính thuần ở dạng đơn giản để test trực tiếp.

## 4. Bắt đầu bằng characterization test

Với mã cũ, ta thường không có đặc tả đầy đủ. Trước khi di chuyển phụ thuộc, hãy ghi nhận hành vi đang có bằng **characterization test**.

Test này trả lời: “Với đầu vào và điều kiện này, hệ thống hiện đang làm gì?” Nó giúp tạo một đường cơ sở để refactor không vô tình thay đổi hành vi ngoài dự kiến.

Ví dụ, nếu phương thức định dạng số dư hiện tạo nội dung như sau:

~~~java
final class StatementFormatter {
    String format(long balanceVnd, long generatedAtMillis) {
        return "Balance: " + balanceVnd
                + ", generatedAt: " + generatedAtMillis;
    }
}
~~~

Có thể ghi nhận kết quả hiện tại:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class StatementFormatterTest {
    @Test
    void formatsBalanceAndTimestamp() {
        StatementFormatter formatter = new StatementFormatter();

        assertEquals(
                "Balance: 250000, generatedAt: 1735689600000",
                formatter.format(250_000L, 1_735_689_600_000L));
    }
}
~~~

Test này không khẳng định format hiện tại là thiết kế tốt nhất. Nó đóng vai trò **mốc hành vi** trong lúc ta tạo seam.

### Characterization test khác test đặc tả như thế nào?

- **Characterization test** ghi nhận hành vi hiện có, kể cả những hành vi chưa được tài liệu mô tả.
- **Test đặc tả** xác minh hành vi mong muốn theo yêu cầu đã xác nhận.
- **Regression test** bảo vệ một hành vi hoặc lỗi đã được sửa để không tái xuất hiện.

Nếu phát hiện defect khi ghi nhận hiện trạng, đừng âm thầm biến defect thành yêu cầu chỉ vì test cũ đang xanh. Ghi rõ hành vi hiện tại, xác nhận kết quả mong muốn và viết test đặc tả riêng cho sửa lỗi.

### Không cần đóng băng mọi hành vi cũ

Mã cũ có thể có hành vi ngẫu nhiên, phụ thuộc timezone máy, thứ tự database hoặc dữ liệu test không ổn định. Chỉ ghi nhận hành vi có ý nghĩa và cần bảo vệ. Nếu test snapshot toàn bộ output không ổn định, hãy kiểm soát nguồn thời gian hoặc chỉ assert phần hợp đồng cần giữ.

## 5. Seam qua constructor injection

Cách trực tiếp để tạo seam trong Java là đưa dependency vào constructor. Thay vì tự tạo database repository và email client bên trong phương thức, lớp nhận các thành phần cần dùng từ bên ngoài.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

interface BalanceRepository {
    long findBalanceVnd(long customerId);
}

interface StatementSender {
    void send(long customerId, String content);
}

final class StatementService {
    private final BalanceRepository balances;
    private final StatementSender sender;
    private final Clock clock;

    StatementService(
            BalanceRepository balances,
            StatementSender sender,
            Clock clock
    ) {
        this.balances = Objects.requireNonNull(balances);
        this.sender = Objects.requireNonNull(sender);
        this.clock = Objects.requireNonNull(clock);
    }

    void sendStatement(long customerId) {
        long balanceVnd = balances.findBalanceVnd(customerId);
        Instant generatedAt = clock.instant();

        String content = "Balance: " + balanceVnd
                + ", generatedAt: " + generatedAt.toEpochMilli();

        sender.send(customerId, content);
    }
}
~~~

Điểm quan trọng:

- `StatementService` không biết repository dùng JDBC hay in-memory.
- Nó không tự khởi tạo SMTP client.
- Thời gian được cấp từ bên ngoài.
- Test có thể kiểm soát dữ liệu, thời gian và việc gửi email.
- Mã khởi tạo ứng dụng vẫn có thể nối các implementation thật.

### Composition root: nơi nối implementation thật

Trong ứng dụng thật, một lớp khởi tạo hoặc dependency injection container tạo các adapter production rồi truyền vào service:

~~~java
Clock clock = Clock.systemUTC();
BalanceRepository repository = new JdbcBalanceRepository(dataSource);
StatementSender sender = new SmtpStatementSender(smtpClient);

StatementService service =
        new StatementService(repository, sender, clock);
~~~

Đây là composition root: vị trí biết cả logic ứng dụng và hạ tầng cụ thể để nối chúng. Phần còn lại của ứng dụng không cần tự tạo dependency ở nhiều nơi.

Constructor injection làm dependency nhìn thấy ngay khi tạo object. Nếu lớp cần ba thành phần để hoạt động, chữ ký constructor thể hiện điều đó. Nó cũng giúp test không phải sửa trạng thái private hoặc dùng reflection để cài dependency.

## 6. Kiểm thử bằng fake thay vì kết nối dịch vụ thật

Một fake có hành vi đơn giản nhưng đủ thực tế cho test. Ví dụ:

~~~java
import java.util.HashMap;
import java.util.Map;

final class InMemoryBalanceRepository implements BalanceRepository {
    private final Map<Long, Long> balances = new HashMap<>();

    void put(long customerId, long balanceVnd) {
        balances.put(customerId, balanceVnd);
    }

    @Override
    public long findBalanceVnd(long customerId) {
        Long value = balances.get(customerId);
        if (value == null) {
            throw new IllegalArgumentException("Customer not found");
        }
        return value;
    }
}

final class RecordingStatementSender implements StatementSender {
    private long lastCustomerId;
    private String lastContent;

    @Override
    public void send(long customerId, String content) {
        lastCustomerId = customerId;
        lastContent = content;
    }

    long lastCustomerId() {
        return lastCustomerId;
    }

    String lastContent() {
        return lastContent;
    }
}
~~~

Unit test dùng dữ liệu và thời gian cố định:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class StatementServiceTest {
    @Test
    void sendsStatementWithBalanceAndFixedTime() {
        InMemoryBalanceRepository repository =
                new InMemoryBalanceRepository();
        repository.put(42L, 250_000L);

        RecordingStatementSender sender =
                new RecordingStatementSender();

        Clock fixedClock = Clock.fixed(
                Instant.parse("2025-01-01T00:00:00Z"),
                ZoneOffset.UTC);

        StatementService service =
                new StatementService(repository, sender, fixedClock);

        service.sendStatement(42L);

        assertEquals(42L, sender.lastCustomerId());
        assertEquals(
                "Balance: 250000, generatedAt: 1735689600000",
                sender.lastContent());
    }
}
~~~

Test chạy không cần PostgreSQL hoặc SMTP. Nó kiểm tra rằng service lấy đúng số dư, dùng thời điểm được cấp và gửi đúng nội dung tới sender.

### Fake, stub, mock và spy

Các thuật ngữ có thể được dùng hơi khác nhau giữa các thư viện, nhưng thường phân biệt như sau:

| Test double | Mục đích | Ví dụ |
| --- | --- | --- |
| **Stub** | Trả dữ liệu đã định trước | Repository luôn trả số dư 250.000 |
| **Fake** | Implementation đơn giản nhưng có hành vi | Repository lưu dữ liệu trong Map |
| **Mock** | Theo dõi và xác minh tương tác | Xác minh sender được gọi đúng một lần |
| **Spy** | Bao quanh implementation thật để quan sát một phần | Ghi lại lời gọi rồi chuyển tiếp |

Không cần chọn mock cho mọi dependency. Fake thường hữu ích khi cần một hành vi có thể đọc và tái sử dụng; stub phù hợp khi chỉ cần một response; mock hữu ích khi **tương tác là một phần hợp đồng**, chẳng hạn không được gửi email hai lần.

Tránh xác minh quá nhiều lời gọi nội bộ không thuộc hợp đồng. Test nên ưu tiên kết quả và side effect có ý nghĩa, để refactor cấu trúc không làm hàng loạt test thất bại dù hành vi vẫn đúng.

## 7. Tách phụ thuộc thời gian bằng Clock

Một trong những phụ thuộc dễ bỏ sót là thời gian hiện tại. Mã gọi trực tiếp `LocalDate.now()` hoặc `Instant.now()` có thể cho kết quả khác nhau theo ngày chạy, timezone hoặc thời điểm biên.

Ví dụ tính hạn thanh toán:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

final class PaymentDeadline {
    private final Clock clock;

    PaymentDeadline(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    boolean isOverdue(LocalDate dueDate) {
        LocalDate today = LocalDate.now(clock);
        return today.isAfter(dueDate);
    }
}
~~~

Test có thể cố định ngày:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class PaymentDeadlineTest {
    @Test
    void isNotOverdueOnDueDate() {
        Clock clock = Clock.fixed(
                Instant.parse("2025-03-10T10:00:00Z"),
                ZoneOffset.UTC);

        PaymentDeadline deadline = new PaymentDeadline(clock);

        assertFalse(deadline.isOverdue(LocalDate.of(2025, 3, 10)));
    }

    @Test
    void becomesOverdueAfterDueDate() {
        Clock clock = Clock.fixed(
                Instant.parse("2025-03-11T00:00:00Z"),
                ZoneOffset.UTC);

        PaymentDeadline deadline = new PaymentDeadline(clock);

        assertTrue(deadline.isOverdue(LocalDate.of(2025, 3, 10)));
    }
}
~~~

`Clock.fixed` làm test lặp lại. Trong production có thể truyền `Clock.systemUTC()` hoặc một clock theo vùng nghiệp vụ đã xác định.

### Cẩn thận với timezone và ngày địa phương

Nếu hạn thanh toán được định nghĩa theo ngày địa phương của cửa hàng, `LocalDate.now(clock)` cần dùng clock có `ZoneId` tương ứng. Không nên mặc định UTC nếu nghiệp vụ dựa trên timezone cửa hàng. Seam giúp test điều kiện biên, nhưng **đặc tả timezone vẫn phải được xác nhận**.

## 8. Tạo seam cho filesystem, mạng và số ngẫu nhiên

Không phải lúc nào cũng cần tạo một interface tổng quát. Một adapter nhỏ quanh API ngoài có thể đủ.

### Filesystem

Thay vì để logic nghiệp vụ trực tiếp gọi `Files.writeString`, tạo một cổng lưu nội dung:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

interface StatementStore {
    void save(long customerId, String content) throws IOException;
}

final class FileStatementStore implements StatementStore {
    private final Path directory;

    FileStatementStore(Path directory) {
        this.directory = directory;
    }

    @Override
    public void save(long customerId, String content) throws IOException {
        Files.createDirectories(directory);
        Files.writeString(
                directory.resolve(customerId + ".txt"),
                content);
    }
}
~~~

Trong unit test service, có thể dùng fake `StatementStore` ghi lại nội dung. Trong integration test adapter, dùng thư mục tạm của test để kiểm tra file thực được tạo, encoding và xử lý lỗi.

### HTTP hoặc dịch vụ bên ngoài

Một interface như `ExchangeRateProvider` có thể cho phép truyền tỷ giá cố định trong unit test. Adapter production thực hiện HTTP, timeout và parse response; test adapter kiểm tra serialization, status code và xử lý lỗi ở mức tích hợp.

Không nên fake HTTP trong mọi test rồi kết luận adapter hoạt động đúng. Cần ít nhất một tập test phù hợp xác minh request/response thật hoặc một contract test với server giả có hành vi được kiểm soát.

### Số ngẫu nhiên

Nếu logic dùng `new Random()` bên trong, test khó tái tạo một chuỗi cụ thể. Có thể truyền `RandomGenerator` hoặc một abstraction nhỏ để cấp giá trị có seed cố định. Chỉ làm vậy khi tính ngẫu nhiên ảnh hưởng đến hành vi cần kiểm tra; không cần tạo framework random cho một đoạn code không có yêu cầu kiểm thử đặc biệt.

## 9. Bao phụ thuộc static, singleton và khởi tạo trực tiếp

Mã cũ thường gọi API static hoặc tự tạo object:

~~~java
final class LegacyInvoiceService {
    Invoice create(long customerId) {
        Customer customer = CustomerRegistry.get(customerId);
        String id = IdGenerator.next();
        Instant now = Instant.now();

        return new Invoice(id, customerId, customer.name(), now);
    }
}
~~~

Các lời gọi static và singleton làm nguồn dữ liệu ẩn. Test khó thay registry, ID generator và clock; trạng thái toàn cục có thể rò rỉ giữa test.

Một cách chuyển đổi là tạo adapter ở ranh giới:

~~~java
interface CustomerLookup {
    Customer find(long customerId);
}

interface InvoiceIdGenerator {
    String nextId();
}

final class LegacyCustomerLookup implements CustomerLookup {
    @Override
    public Customer find(long customerId) {
        return CustomerRegistry.get(customerId);
    }
}

final class LegacyInvoiceIdGenerator implements InvoiceIdGenerator {
    @Override
    public String nextId() {
        return IdGenerator.next();
    }
}
~~~

Sau đó service nhận các dependency này qua constructor, tương tự phần 5. Mã gọi static vẫn tồn tại trong adapter, nhưng logic nghiệp vụ không còn phụ thuộc trực tiếp vào singleton.

### Không phải mọi static method đều cần bọc

Một hàm thuần như `Math.max(a, b)` hoặc parser không trạng thái, xác định có thể gọi trực tiếp. Seam cần thiết khi dependency có **nguồn dữ liệu, trạng thái, thời gian, môi trường hoặc tác dụng phụ** cần thay thế trong test.

Nếu bọc mọi hàm static bằng interface, thiết kế sẽ phình ra mà không tăng khả năng kiểm thử có ý nghĩa.

## 10. Seam qua tham số hàm và factory

Một số logic chỉ cần một giá trị biến thiên, không cần dependency object.

Ví dụ hàm lọc hóa đơn theo thời điểm có thể nhận `today`:

~~~java
import java.time.LocalDate;
import java.util.List;

final class InvoiceFilter {
    List<Invoice> overdueInvoices(
            List<Invoice> invoices,
            LocalDate today
    ) {
        return invoices.stream()
                .filter(invoice -> invoice.dueDate().isBefore(today))
                .toList();
    }
}
~~~

Hàm thuần này không cần biết đồng hồ hệ thống. Lớp điều phối bên ngoài có thể đọc ngày từ `Clock` rồi truyền vào. Cách đó giữ logic đơn giản và làm điều kiện kiểm thử hiện rõ.

Factory là seam hữu ích khi đối tượng được tạo bên trong một luồng nhưng cách tạo cần thay đổi:

- Factory thật tạo kết nối/adapter theo cấu hình production.
- Factory test tạo implementation nhẹ.
- Test có thể xác minh đối tượng được tạo với cấu hình đúng.

Tuy nhiên, nếu chỉ có một dependency ổn định, truyền thẳng dependency vào constructor thường dễ đọc hơn một factory tổng quát.

## 11. Tách phụ thuộc theo bước nhỏ trong mã hiện hữu

Không nên bắt đầu bằng việc viết lại toàn bộ module. Một lộ trình ít rủi ro:

1. **Chọn một hành vi có giá trị:** nơi đang khó test hoặc thường gây lỗi.
2. **Đọc đường gọi và phụ thuộc:** xác định ai tạo object, ai sở hữu transaction, ai thực hiện I/O.
3. **Ghi nhận hành vi:** thêm characterization test cho đầu vào và kết quả quan trọng.
4. **Chọn seam nhỏ nhất:** truyền Clock, repository, sender hoặc adapter cụ thể.
5. **Chuyển khởi tạo ra ngoài:** giữ nơi nối implementation thật ở composition root.
6. **Viết test double:** fake/stub kiểm soát được dữ liệu và side effect.
7. **Chạy test và so hành vi:** xác nhận refactor không làm đổi contract ngoài ý muốn.
8. **Thêm integration test ở adapter:** kiểm tra phần tương tác với DB, file hoặc mạng thật.
9. **Loại đường phụ thuộc cũ:** tránh giữ hai cách khởi tạo làm người sau tiếp tục dùng đường khó test.
10. **Lặp lại khi có bằng chứng:** chỉ mở rộng sang vùng khác khi lợi ích rõ.

~~~mermaid
flowchart TD
    A["Chọn hành vi khó test"] --> B["Đọc caller và phụ thuộc"]
    B --> C["Characterization test"]
    C --> D["Tạo seam nhỏ"]
    D --> E["Tiêm dependency từ bên ngoài"]
    E --> F["Test với fake / fixed clock"]
    F --> G["Integration test adapter"]
    G --> H{"Hành vi và contract được giữ?"}
    H -->|"Chưa"| I["Điều tra / sửa / rollback bước vừa đổi"]
    I --> C
    H -->|"Có"| J["Loại đường phụ thuộc cũ"]
    J --> K["Ghi nhận ranh giới mới"]
~~~

### Khi cần làm từng bước vì test chưa đủ

Có thể thêm một constructor mới nhận dependency và giữ constructor cũ tạm thời để tương thích. Nhưng constructor cũ nên có lộ trình loại bỏ; nếu cả hai tồn tại lâu, code mới có thể tiếp tục dùng đường cũ và seam không đem lại giá trị.

Không xóa hoặc đổi behavior chỉ vì muốn cấu trúc đẹp hơn. Tách phụ thuộc trước, sau đó xử lý defect hoặc thay đổi nghiệp vụ thành bước có chủ đích và có test riêng.

## 12. Chọn đúng loại test double

Test double nên mô hình hóa **hợp đồng mà logic cần**, không sao chép toàn bộ hạ tầng.

Ví dụ với `BalanceRepository`:

- Unit test `StatementService`: fake trả số dư theo customer ID.
- Test `JdbcBalanceRepository`: database test xác minh SQL, mapping và xử lý bản ghi thiếu.
- Contract test: xác nhận implementation thật và fake cùng đáp ứng các hành vi quan trọng nếu fake được dùng rộng.
- End-to-end: kiểm tra luồng từ request tới kết quả khi rủi ro yêu cầu.

### Fake quá đơn giản cũng có thể che lỗi

Fake trong Map không có transaction, constraint, collation, isolation hay SQL null semantics như PostgreSQL. Nếu chỉ dùng fake, test có thể xanh trong khi repository thật sai.

Do đó:

- Dùng fake để kiểm tra logic gọi repository.
- Dùng database integration test để kiểm tra SQL và mapping.
- Dùng test theo hợp đồng nếu có nhiều implementation.
- Không mô phỏng toàn bộ database trong một fake tự viết nếu chi phí duy trì cao hơn dùng test container hoặc DB test phù hợp.

### Mock tương tác hay kiểm tra trạng thái?

Nếu hợp đồng là “gửi một email với nội dung này”, recording fake có thể kiểm tra kết quả gửi. Nếu hợp đồng là “không gửi email khi dữ liệu không hợp lệ”, mock/spy có thể xác minh không có lời gọi. Nhưng không nên kiểm tra từng getter hoặc method private vì đó là chi tiết implementation.

## 13. Seam không được làm yếu kiểm thử bảo mật

Tạo fake có thể khiến test dễ viết, nhưng cần cẩn thận không thay thế những kiểm soát bảo mật quan trọng bằng giả định.

Ví dụ:

- Fake `Actor` không được lấy quyền từ dữ liệu do client kiểm soát nếu production lấy từ token đã xác minh.
- Fake repository có thể lọc tenant trong Map nhưng SQL production quên điều kiện tenant.
- Fake payment gateway có thể luôn thành công trong khi adapter thật có timeout sau khi đã xử lý giao dịch.
- Fake file store không kiểm tra quyền filesystem hoặc symlink.
- Fake clock không mô phỏng được hết timezone và chuyển đổi lịch.

Vì vậy, kiểm thử quyền truy cập cần test logic policy **và** kiểm tra ranh giới truy vấn/HTTP thực tế ở nơi có nguy cơ. Seam tăng khả năng kiểm soát test, không thay thế bằng chứng từ integration test.

## 14. Khi một seam trở thành abstraction thừa

Một số dấu hiệu cho thấy ta đã tạo quá nhiều lớp:

- Interface chỉ có một implementation, không có biến thể cần thiết và không tạo ranh giới test hữu ích.
- Mỗi method chỉ chuyển tiếp tham số sang lớp kế tiếp.
- Test phải dựng mười object chỉ để gọi một phép tính thuần.
- Một `FactoryProviderRegistry` được thêm chỉ để thay một hàm gọi thời gian.
- Tên abstraction chung chung không nói rõ dependency hoặc trách nhiệm.
- Test double phải mô phỏng rất nhiều method mà logic không dùng.
- Mỗi thay đổi nhỏ phải sửa nhiều interface/adapter không cần thiết.

Có thể dùng `Clock` chuẩn của Java thay vì tạo `TimeService` riêng chỉ để trả về thời gian hiện tại. Có thể truyền `LocalDate` vào một hàm thuần thay vì tạo interface cho mọi phép tính ngày.

**Seam tốt là seam có ích cho một ranh giới biến thiên thực tế và làm test/logic dễ hiểu hơn.**

### Đừng tối ưu chỉ để mock được

Nếu test buộc phải mock private method hoặc dùng reflection để thay field, có thể lớp đang có quá nhiều trách nhiệm. Nhưng giải pháp không phải tự động thêm interface cho từng method. Hãy tìm **ranh giới nghiệp vụ hoặc hạ tầng** mà tại đó một dependency có thể được cung cấp từ bên ngoài.

## 15. Các vấn đề thường gặp khi đưa seam vào legacy code

| Vấn đề | Vì sao xảy ra | Hướng xử lý |
| --- | --- | --- |
| Constructor có quá nhiều tham số | Lớp đang sở hữu nhiều trách nhiệm hoặc thiếu object gom nhóm có ý nghĩa | Xem lại ranh giới; chỉ gom dependency có cùng vòng đời/trách nhiệm |
| Test phải tạo nhiều fake | Logic đang phụ thuộc quá nhiều collaborator | Tách logic thuần hoặc thu hẹp interface; không tạo mock chung toàn hệ thống |
| Fake và production khác hành vi | Fake không mô hình hóa hợp đồng thật | Bổ sung contract/integration tests |
| Test phụ thuộc thứ tự chạy | Dùng static/global mutable state | Loại trạng thái toàn cục hoặc reset qua lifecycle rõ |
| Test thời gian lúc xanh lúc đỏ | Đọc đồng hồ thật hoặc phụ thuộc timezone máy | Tiêm Clock và xác định ZoneId |
| Test gọi API thật | Dependency chưa được thay ở boundary | Tạo adapter seam và test contract riêng |
| Refactor làm thay đổi output | Characterization test thiếu hoặc đặc tả không rõ | Xác nhận hành vi, bổ sung test, tách defect khỏi refactor |
| Có cả constructor cũ và mới | Migration chưa hoàn tất | Đánh dấu deprecated nếu phù hợp, chuyển caller và đặt mốc loại bỏ |
| Mock quá chi tiết | Test phụ thuộc cách cài đặt | Assert kết quả/side effect thuộc hợp đồng |
| Một interface chung quá rộng | Nhiều domain bị ép chung | Tách port theo nhu cầu của consumer |

## 16. Review chất lượng của một test seam

Khi review thay đổi tạo seam, hãy hỏi:

1. Dependency nào trước đây bị tạo hoặc truy cập bên trong lớp?
2. Vì sao dependency đó cần thay thế trong test?
3. Seam mới nằm ở ranh giới có ý nghĩa hay chỉ thêm một lớp chuyển tiếp?
4. Logic nghiệp vụ có còn rõ và không bị trộn với I/O?
5. Production có nối đúng adapter thật ở composition root không?
6. Test double có phản ánh hợp đồng cần thiết và có giới hạn rõ không?
7. Có integration/contract test cho phần fake không thể chứng minh không?
8. Thời gian, timezone, random và global state có còn làm test không xác định không?
9. Có làm thay đổi API công khai hoặc caller cũ không?
10. Có thể loại bỏ đường khởi tạo cũ sau migration không?

Một nhận xét review có ích:

> “Việc truyền Clock vào constructor giúp test cố định thời điểm. Mình muốn xác nhận production vẫn dùng ZoneId của cửa hàng cho hạn thanh toán; test hiện dùng UTC. Bạn có thể thêm một trường hợp gần nửa đêm theo timezone nghiệp vụ hoặc giải thích vì sao UTC là hợp đồng ở đây không?”

Nhận xét tập trung vào **độ đúng của seam và hợp đồng thời gian**, không chỉ yêu cầu “thêm mock”.

## 17. Ví dụ quyết định: nên tạo seam ở đâu?

Giả sử một lớp xử lý đơn hàng:

- Tính tổng tiền.
- Đọc ngày hiện tại.
- Truy vấn tồn kho.
- Gửi yêu cầu giữ hàng.
- Lưu đơn hàng.

Không cần biến từng phép toán thành dependency. Có thể phân loại:

| Thành phần | Có nên tạo seam? | Lý do |
| --- | --- | --- |
| Cộng các dòng hàng thuần | Thường không | Đầu vào/đầu ra xác định, test trực tiếp |
| Quy tắc ngày hết hạn | Có thể truyền Clock hoặc ngày | Cần kiểm tra thời điểm và timezone |
| Truy vấn tồn kho | Có | Database hoặc dịch vụ ngoài |
| Gửi yêu cầu giữ hàng | Có | Side effect và failure/retry |
| Lưu đơn hàng | Có | Persistence và transaction |
| Định dạng chuỗi cố định | Thường không | Hàm thuần, không có môi trường ngoài |

Đây là cách tránh **seam hóa toàn bộ code**. Ta chỉ mở điểm tách nơi phụ thuộc cần kiểm soát hoặc có ranh giới tích hợp.

## 18. Checklist thực hành

### Trước khi thay đổi

- [ ] Tôi đã xác định hành vi cần kiểm tra và lý do test hiện tại khó viết.
- [ ] Tôi đã đọc caller và cách dependency được tạo.
- [ ] Tôi phân biệt logic thuần với I/O và tác dụng phụ.
- [ ] Tôi đã ghi nhận hành vi hiện tại bằng test phù hợp.
- [ ] Tôi đã xác nhận hành vi nào là hợp đồng, hành vi nào là defect.

### Khi tạo seam

- [ ] Seam nằm ở ranh giới có ý nghĩa.
- [ ] Dependency được truyền từ bên ngoài thay vì tự tạo sâu bên trong logic.
- [ ] Tên interface/adapter thể hiện trách nhiệm.
- [ ] Không tạo interface chỉ vì mọi class “nên có interface”.
- [ ] Clock, timezone, random và global state được kiểm soát khi ảnh hưởng kết quả.
- [ ] Composition root nối implementation production rõ ràng.
- [ ] Constructor và API không bị mở rộng tùy tiện.

### Khi kiểm thử

- [ ] Fake/stub/mock được chọn theo hợp đồng cần kiểm tra.
- [ ] Test assert kết quả và side effect có ý nghĩa.
- [ ] Có test cho trường hợp lỗi và biên.
- [ ] Adapter thật được kiểm tra bằng integration/contract test khi cần.
- [ ] Không dùng fake để thay thế bằng chứng về SQL, quyền hoặc giao tiếp thật.
- [ ] Test không phụ thuộc thứ tự, giờ hệ thống hoặc trạng thái toàn cục.

### Sau khi refactor

- [ ] Hành vi được giữ hoặc thay đổi theo đặc tả đã xác nhận.
- [ ] Đường tạo dependency cũ được loại bỏ hoặc có kế hoạch chuyển đổi.
- [ ] Các caller quan trọng đã dùng seam mới.
- [ ] Test đủ nhanh và dễ chẩn đoán hơn ở phạm vi mục tiêu.
- [ ] Abstraction mới không tạo coupling hoặc boilerplate không cần thiết.

## 19. Những ngộ nhận thường gặp

**“Muốn test được thì phải có interface.”** Một constructor nhận Clock, một tham số LocalDate hoặc một hàm thuần có thể đủ. Interface chỉ hữu ích khi cần ranh giới hợp đồng hoặc nhiều implementation.

**“Mock tất cả dependency thì test đã độc lập.”** Mock quá nhiều có thể khiến test chỉ xác minh cách gọi nội bộ, trong khi hành vi thật không được kiểm tra.

**“Fake repository chứng minh SQL đúng.”** Fake không chạy SQL; cần integration test cho query, mapping, constraint và transaction.

**“Mã cũ phải viết lại trước mới test được.”** Có thể bắt đầu bằng characterization test, thêm một seam nhỏ và chuyển dần caller.

**“Static method nào cũng phải bọc.”** Hàm thuần, xác định có thể gọi trực tiếp; ưu tiên bọc dependency có trạng thái hoặc tác dụng phụ.

**“Clock cố định là đủ cho mọi test thời gian.”** Còn phải xác định timezone, lịch địa phương, daylight saving và quy tắc ngày nghiệp vụ.

**“Seam càng nhiều thì test càng tốt.”** Nhiều seam không cần thiết làm thiết kế khó hiểu và test tốn công dựng.

**“Constructor có nhiều dependency nghĩa là chỉ cần gom chúng vào một Context object.”** Nếu các dependency thuộc nhiều trách nhiệm khác nhau, Context chỉ che vấn đề; hãy xem lại ranh giới của lớp.

**“Test seam cho phép bỏ integration test.”** Seam hỗ trợ kiểm tra logic cô lập; adapter và hạ tầng vẫn cần được kiểm tra tại ranh giới thật.

**“Refactor tạo seam có thể đổi luôn hành vi cũ.”** Hãy phân biệt chuyển cấu trúc với sửa defect; xác nhận đặc tả và test riêng.

**“Nếu test xanh thì production đã nối đúng adapter.”** Test unit có thể dùng fake; cần kiểm tra composition root, cấu hình và integration thực tế.

## 20. Bài tập thực hành

### Bài tập A — tìm dependency ẩn

Đọc lớp sau:

~~~java
final class ExpirationService {
    boolean expired(long expiresAtMillis) {
        return System.currentTimeMillis() > expiresAtMillis;
    }
}
~~~

Hãy:
1. Chỉ ra dependency nào làm kết quả thay đổi theo thời điểm chạy.
2. Đề xuất một seam tối thiểu bằng Clock hoặc tham số thời gian.
3. Viết hai test: đúng tại thời điểm hết hạn và sau thời điểm hết hạn.
4. Xác định timezone có liên quan không nếu giá trị được định nghĩa là epoch milliseconds.

### Bài tập B — thêm seam mà không viết lại module

Một lớp cũ tự tạo JDBC connection, gọi SMTP và ghi file. Hãy chọn thứ tự tách dependency. Với mỗi bước, nêu characterization test, seam, test double và integration test cần thiết.

### Bài tập C — fake hay integration test?

Một repository có phương thức tìm đơn theo ID và tenant. Hãy phân loại bằng chứng cần có cho:
- Logic service từ chối tenant khác.
- SQL thật có điều kiện tenant.
- Mapping khi không tìm thấy bản ghi.
- Timeout và lỗi kết nối.
- Serialization của response HTTP.

Giải thích vì sao một fake trong Map không thể chứng minh tất cả.

### Bài tập D — nhận diện abstraction thừa

Một lớp ApplicationContext có 28 dependency, mỗi service đều nhận toàn bộ context dù chỉ dùng hai dependency. Hãy phân tích vì sao đây chưa chắc là cải thiện testability. Đề xuất cách thu hẹp dependency theo constructor và trách nhiệm.

### Bài tập E — refactor có kiểm soát

Một service dùng singleton SystemSettings.current() để đọc cấu hình và static IdGenerator.next(). Viết kế hoạch chuyển đổi từng bước, bao gồm test trước refactor, adapter, constructor injection, composition root và cách loại đường gọi cũ.

## 21. Câu hỏi tự kiểm tra

1. Test seam là gì? Phân biệt seam, dependency và test double.
2. Vì sao một lớp vừa đọc database vừa gửi email khó được kiểm tra như một đơn vị?
3. Characterization test giúp gì khi đặc tả mã cũ chưa đầy đủ?
4. Vì sao cần phân biệt hành vi hiện tại với hành vi mong muốn?
5. Constructor injection tạo seam như thế nào?
6. Composition root có trách nhiệm gì?
7. Khi nào nên dùng fake, stub, mock hoặc spy?
8. Vì sao test dùng fake repository không chứng minh SQL production đúng?
9. Clock.fixed giúp kiểm thử thời gian ra sao? Còn vấn đề timezone nào cần quan tâm?
10. Khi nào một static method không cần được bọc bằng interface?
11. Làm sao tạo seam cho filesystem mà vẫn test adapter ghi file thật?
12. Vì sao không nên mock mọi method nội bộ?
13. Một test seam có thể vô tình làm yếu kiểm thử bảo mật thế nào?
14. Khi nào truyền tham số thời gian trực tiếp tốt hơn tạo TimeService?
15. Vì sao constructor có quá nhiều dependency có thể là dấu hiệu lớp đang ôm nhiều trách nhiệm?
16. Những test nào nên chạy ở cấp unit, component, integration và contract?
17. Cách chuyển đổi từng bước giúp giảm rủi ro với legacy code ra sao?
18. Làm sao biết seam mới thực sự làm test dễ hơn thay vì chỉ thêm boilerplate?
19. Vì sao cần kiểm tra composition root sau khi unit test đã xanh?
20. Hãy đề xuất một seam cho dependency khó kiểm thử trong hệ thống bạn biết, kèm test double và giới hạn của nó.

## Ghi nhớ

**Tạo điểm tách phụ thuộc là làm cho logic cần kiểm tra có thể nhận dữ liệu và điều khiển tác dụng phụ từ bên ngoài.** Hãy bắt đầu bằng việc hiểu hành vi hiện có, ghi nhận hợp đồng bằng characterization test, rồi tách database, mạng, filesystem, thời gian hoặc trạng thái toàn cục ở ranh giới có ý nghĩa. Dùng fake và fixed clock để kiểm tra logic; dùng integration/contract test để xác minh adapter thật. Không cần interface cho mọi hàm và không dùng mock để che hạ tầng quan trọng. Một seam tốt giúp test ổn định hơn, làm rõ trách nhiệm và cho phép cải thiện mã cũ từng bước mà vẫn bảo vệ **tính đúng đắn, độ tin cậy và khả năng thay đổi**.
