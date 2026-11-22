# Tạo interface hoặc factory không có nhu cầu thay thế hay quản lý vòng đời

## 1. Khi muốn “đúng DI” nhưng lại làm thiết kế phức tạp hơn

**Dependency Injection (DI)** tách việc **sử dụng phụ thuộc** khỏi việc **tạo và lắp ghép đối tượng**. Với Java thuần, một service có thể nhận đối tượng đã được tạo tại **composition root** qua constructor, không cần framework hoặc DI container.

Một lỗi thiết kế phổ biến là hiểu DI thành quy tắc cứng:

> Mọi lớp phải có interface; mọi đối tượng phải được tạo qua factory; không được viết `new`.

Kết quả có thể là hàng loạt lớp `IOrderFormatter`, `OrderFormatterImpl`, `OrderFormatterFactory` và `OrderFormatterFactoryImpl` dù ứng dụng chỉ có một thuật toán định dạng ổn định, không cần tạo phiên làm việc mới, không có tài nguyên cần đóng và không có lý do thay thế thành phần.

Lúc này, abstraction không che giấu biến động thật mà **tạo thêm điểm chuyển hướng cho người đọc**. Muốn hiểu một phép tính đơn giản, lập trình viên phải mở nhiều file, lần theo binding và tìm xem factory có làm gì ngoài gọi constructor hay không.

Bài học này thuộc chương **Lỗi thiết kế** trong module **DEPENDENCY_INJECTION**. Mục tiêu là phân biệt **constructor injection**, **interface**, **factory**, **provider** và **composition root**; biết khi nào dùng mỗi thứ, tránh *overengineering* mà vẫn giữ khả năng kiểm thử, lựa chọn implementation và quản lý scope/vòng đời khi thực sự cần.

**Điểm cốt lõi:** DI **không yêu cầu interface**; constructor injection có thể nhận một lớp cụ thể. Factory **không phải điều kiện của DI**; `new` tại composition root là cách lắp ghép hợp lệ.

## 2. Nhận diện abstraction không mang lại lợi ích thực tế

Hãy xem một đoạn thiết kế có vẻ “linh hoạt”:

~~~java
// Phác họa: các kiểu phụ thuộc trong cùng một ứng dụng.
interface ReceiptFormatter {
    String format(String id, long totalVnd);
}

final class DefaultReceiptFormatter implements ReceiptFormatter {
    @Override
    public String format(String id, long totalVnd) {
        return id + ": " + totalVnd + " VND";
    }
}

interface ReceiptFormatterFactory {
    ReceiptFormatter create();
}

final class DefaultReceiptFormatterFactory
        implements ReceiptFormatterFactory {
    @Override
    public ReceiptFormatter create() {
        return new DefaultReceiptFormatter();
    }
}
~~~

Nếu **chỉ một formatter** được dùng, nó không có trạng thái theo request, không mở tài nguyên và việc tạo chỉ là gọi constructor rỗng, factory trên không có chính sách nào để điều phối. Một lớp với hàm `format` thuần túy có thể đã đủ:

~~~java
final class ReceiptFormatter {
    String format(String id, long totalVnd) {
        return id + ": " + totalVnd + " VND";
    }
}

final class ReceiptService {
    private final ReceiptFormatter formatter;

    ReceiptService(ReceiptFormatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(
                formatter, "formatter");
    }
}

// Composition root:
ReceiptService service = new ReceiptService(new ReceiptFormatter());
~~~

Những đoạn code trên là ví dụ cấu trúc, không phải các chương trình độc lập có `main`. Constructor injection vẫn hiện diện: `ReceiptService` **không tự tạo formatter trong hành vi nghiệp vụ**; caller quyết định và truyền phụ thuộc.

**Có thể loại bỏ cả constructor injection cho helper thuần túy không?** Có, tùy ranh giới trách nhiệm. Nếu `ReceiptFormatter` là chi tiết nội bộ rất ổn định, service có thể tự sở hữu nó hoặc gọi một hàm thuần. Tuy nhiên, giữ constructor injection cho lớp cụ thể vẫn hữu ích khi muốn composition root quyết định cấu hình và chia sẻ instance. Không cần nâng mọi quyết định lên thành interface/factory.

### Dấu hiệu đáng nghi

- Interface có đúng một implementation, chỉ lặp lại nguyên xi chữ ký mà không có ranh giới/biến thể cần bảo vệ.
- Factory chỉ thực hiện `return new X()`, không nhận tham số runtime, không điều phối scope, cache, tài nguyên hay quy tắc khởi tạo.
- Muốn chỉnh một phép tính phải cập nhật interface, implementation, factory và cấu hình DI mà không có lý do nghiệp vụ.
- Test phải mock các phép tính thuần túy thay vì dùng implementation thật.
- Tên `Impl` hoặc `Factory` xuất hiện vì quy ước, nhưng không trả lời được điều gì có thể thay thế hoặc ai sở hữu sản phẩm.

Đây là **dấu hiệu để điều tra**, không phải bằng chứng tự động rằng abstraction sai. Một interface chỉ có một implementation vẫn có thể là **port có giá trị** nếu ngăn core phụ thuộc SDK/DB/mạng hoặc tạo seam cho kiểm thử tác dụng phụ.

## 3. Interface là hợp đồng: nên được tạo vì ranh giới hoặc biến động

**Interface** mô tả những khả năng mà một bên sử dụng cần. Nó có lợi khi có **lý do thiết kế cụ thể**, không chỉ để áp dụng Dependency Inversion Principle (DIP) theo hình thức.

| Tình huống | Interface có thể hữu ích? | Lý do |
| --- | --- | --- |
| Hai thuật toán/chính sách có thể thay thế | Có | Consumer phụ thuộc cùng hợp đồng thay vì từng thuật toán |
| Giao tiếp bên ngoài: gửi email, HTTP, thanh toán, lưu DB | Thường có | Tách core khỏi I/O và SDK; test được với fake |
| Một module ổn định cần cách ly implementation của module khác | Có thể | Ranh giới kiến trúc và quyền sở hữu thay đổi rõ ràng |
| Chỉ có một phép tính bất biến, không I/O | Thường không cần | Lớp cụ thể hoặc hàm thuần đủ đơn giản |
| Test cần giả lập lỗi/độ trễ của hạ tầng | Thường có | Port cho phép fake mô phỏng hành vi thất bại |
| Dự đoán mơ hồ “mai sau biết đâu thay” | Chưa đủ | Có thể refactor khi nhu cầu xuất hiện, tránh thiết kế quá sớm |

**Số implementation hiện tại không phải tiêu chí duy nhất.** Ví dụ, `PaymentGateway` có thể chỉ có một adapter production nhưng vẫn là port hợp lý vì nghiệp vụ không nên phụ thuộc trực tiếp vào SDK thanh toán, và unit test cần tránh charge thật.

Ngược lại, `ShippingCalculator` với một công thức ổn định và thuần túy chưa cần `ShippingCalculatorInterface` chỉ để sử dụng constructor injection. Trong unit test, có thể dùng **calculator thật** vì nó rẻ, tất định và không gây tác dụng phụ.

### Phân biệt DI và DIP

- **DI:** đối tượng nhận phụ thuộc từ bên ngoài; kiểu phụ thuộc có thể là class, abstract class hoặc interface.
- **DIP:** các chính sách cấp cao tránh phụ thuộc vào chi tiết cấp thấp, thông qua abstraction ở ranh giới có ý nghĩa.

Dùng DI container, thêm interface hoặc thêm hậu tố `Impl` **không tự động** tạo ra một kiến trúc tuân thủ DIP. Chất lượng phụ thuộc phụ thuộc vào việc hợp đồng mô tả **nhu cầu của bên sử dụng**, không sao chép nguyên một API lớn của bên cung cấp.

## 4. Factory không phải lớp vỏ bắt buộc quanh constructor

**Factory** là thành phần tạo ra sản phẩm theo một hợp đồng. Nó đáng giá khi việc tạo sản phẩm mang một quyết định mà caller không nên tự thực hiện.

Một factory có thể hữu ích nếu:

1. **Cần tham số chỉ biết lúc chạy**, ví dụ `reportId`, đường dẫn xuất hoặc cấu hình của một request.
2. **Mỗi tác vụ cần instance mới** có trạng thái riêng, transaction, buffer hoặc session.
3. **Tạo một object graph phức tạp**, cần kiểm tra các điều kiện và dọn tài nguyên nếu khởi tạo giữa chừng thất bại.
4. **Trì hoãn tạo** phụ thuộc tốn chi phí cho đến lần sử dụng; factory/provider thể hiện thời điểm tạo.
5. **Cần chính sách pooling, caching hoặc lựa chọn implementation** mà composition root không thể đơn giản cấp một instance cố định.

Nhưng factory **không cần thiết** nếu kết quả là một đối tượng thuần, tạo nhanh, không có state cần cô lập và constructor đã đủ để mô tả mọi đầu vào.

~~~java
// Một wrapper có thể không mang thêm giá trị.
final class EmptyHelperFactory {
    Helper create() {
        return new Helper();
    }
}
~~~

Nếu `Helper` là đối tượng tính toán bất biến, composition root chỉ cần `new Helper()` rồi tiêm nó. Trái lại, nếu `Helper` cần được **tạo mới mỗi request vì state mutable**, cần tham số runtime hoặc quản lý một resource, factory có thể chính là seam đúng.

**Điểm quan trọng:** tên `Factory` không tự quy định tạo mới mỗi lần, và `Supplier<T>.get()` cũng không hứa tạo mới, cache hay quản lý vòng đời. Hợp đồng factory phải nói rõ *khi nào tạo, sản phẩm sống bao lâu và ai đóng*.

## 5. Bảng lựa chọn: trực tiếp, interface, factory hay provider?

| Nhu cầu thực tế | Giải pháp gọn thường phù hợp | Kiểm tra trước khi chọn |
| --- | --- | --- |
| Lớp thuần túy, bất biến, cấu hình tại startup | Tiêm **lớp cụ thể** qua constructor | Có cần biến thể/ranh giới module không? |
| Một phép tính dùng hoàn toàn nội bộ | Lớp hoặc hàm thuần | Có đang thêm abstraction chỉ để mock không? |
| I/O hoặc SDK bên ngoài cần tách khỏi core | **Port interface** và adapter | Hợp đồng có theo nhu cầu consumer không? |
| Nhiều thuật toán độc lập | **Strategy interface** | Có biến động hành vi thực, không chỉ khác dữ liệu config? |
| Một phiên mới cho mỗi job | **Factory** tạo phiên | Caller có biết khi nào đóng không? |
| Lazy một lần hoặc giải quyết theo scope hiện tại | **Provider/lazy holder** | Có bảo đảm thread safety và vòng đời không? |
| Nhiều dependency nhưng graph đơn giản, ổn định | **Composition root thủ công** | Có thật cần container/factory tổng quát không? |
| Cấu hình phức tạp, nhiều scope, nhiều biến thể | DI container/factory theo ngữ cảnh | Tổng chi phí có giảm không? |

Bảng là công cụ suy nghĩ, **không phải quy tắc tuyệt đối**. Độ biến động của sản phẩm, cấu trúc module, mức độ độc lập của test và yêu cầu vận hành đều có thể làm lựa chọn thay đổi.

## 6. Ví dụ Java thuần: concrete dependency và một port thực sự cần thiết

Ví dụ sau cố tình **không** tạo interface cho máy tính phí vận chuyển vì nó là phép tính nhỏ, ổn định, không có I/O. Trong khi đó, việc ghi biên nhận có tác dụng phụ, nên ta tạo `InvoiceJournal` làm **port** để test không ghi dữ liệu production.

Đồ thị đối tượng:

~~~mermaid
flowchart TB
    Root["App.main / Composition root"]
    Calc["ShippingCalculator (concrete, thuần túy)"]
    Journal["ConsoleInvoiceJournal : InvoiceJournal"]
    Clock["Clock"]
    Service["InvoiceService"]
    Root -->|"tạo cấu hình phí"| Calc
    Root -->|"tạo adapter"| Journal
    Root -->|"cung cấp"| Clock
    Root -->|"constructor injection"| Service
    Service -->|"dùng concrete"| Calc
    Service -->|"dùng port I/O"| Journal
    Service --> Clock
~~~

`InvoiceService` chỉ biết **cách dùng** calculator và journal. Composition root giữ quyết định cách tạo và cung cấp chúng. Một interface thừa cho calculator không làm thiết kế này “DI hơn” nữa.

Lưu chương trình sau thành **`LeanDiDemo.java`**, yêu cầu Java 11 trở lên:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class LeanDiDemo {

    // Concrete dependency: phép tính không I/O, không mutable state.
    public static final class ShippingCalculator {
        private final long standardFeeVnd;
        private final long freeFromVnd;

        public ShippingCalculator(long standardFeeVnd, long freeFromVnd) {
            if (standardFeeVnd < 0 || freeFromVnd <= 0) {
                throw new IllegalArgumentException(
                        "Cấu hình phí/ngưỡng không hợp lệ");
            }
            this.standardFeeVnd = standardFeeVnd;
            this.freeFromVnd = freeFromVnd;
        }

        public long feeFor(long subtotalVnd) {
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException(
                        "subtotalVnd phải dương");
            }
            return subtotalVnd >= freeFromVnd ? 0 : standardFeeVnd;
        }
    }

    // Port có lý do: ranh giới lưu/truyền dữ liệu có tác dụng phụ.
    public interface InvoiceJournal {
        void save(Invoice invoice);
    }

    // Value object là kết quả nghiệp vụ, không cần factory chỉ để tránh new.
    public static final class Invoice {
        private final String id;
        private final long subtotalVnd;
        private final long shippingFeeVnd;
        private final long totalVnd;
        private final Instant createdAt;

        public Invoice(
                String id, long subtotalVnd, long shippingFeeVnd,
                long totalVnd, Instant createdAt) {
            if (id == null || !id.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("id không hợp lệ");
            }
            if (subtotalVnd <= 0 || shippingFeeVnd < 0) {
                throw new IllegalArgumentException("Số tiền không hợp lệ");
            }
            if (totalVnd != Math.addExact(subtotalVnd, shippingFeeVnd)) {
                throw new IllegalArgumentException("Tổng tiền không khớp");
            }
            this.id = id;
            this.subtotalVnd = subtotalVnd;
            this.shippingFeeVnd = shippingFeeVnd;
            this.totalVnd = totalVnd;
            this.createdAt = Objects.requireNonNull(
                    createdAt, "createdAt");
        }

        public String id() { return id; }
        public long subtotalVnd() { return subtotalVnd; }
        public long shippingFeeVnd() { return shippingFeeVnd; }
        public long totalVnd() { return totalVnd; }
        public Instant createdAt() { return createdAt; }
    }

    public static final class InvoiceService {
        private final ShippingCalculator shipping;
        private final InvoiceJournal journal;
        private final Clock clock;

        // Constructor injection chấp nhận cả class và interface.
        public InvoiceService(
                ShippingCalculator shipping,
                InvoiceJournal journal,
                Clock clock) {
            this.shipping = Objects.requireNonNull(shipping, "shipping");
            this.journal = Objects.requireNonNull(journal, "journal");
            this.clock = Objects.requireNonNull(clock, "clock");
        }

        public Invoice issue(String invoiceId, long subtotalVnd) {
            if (invoiceId == null
                    || !invoiceId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException(
                        "invoiceId không hợp lệ");
            }
            if (subtotalVnd <= 0) {
                throw new IllegalArgumentException(
                        "subtotalVnd phải dương");
            }

            long fee = shipping.feeFor(subtotalVnd);
            long total = Math.addExact(subtotalVnd, fee);

            Invoice invoice = new Invoice(
                    invoiceId, subtotalVnd, fee, total, clock.instant());
            journal.save(invoice);
            return invoice;
        }
    }

    // Adapter minh họa: không cần database để chạy bài học.
    public static final class ConsoleInvoiceJournal
            implements InvoiceJournal {
        @Override
        public void save(Invoice invoice) {
            System.out.println(
                    "ISSUED " + invoice.id()
                    + ": subtotal=" + invoice.subtotalVnd()
                    + ", shipping=" + invoice.shippingFeeVnd()
                    + ", total=" + invoice.totalVnd());
        }
    }

    public static void main(String[] args) {
        // Composition root Java thuần, không cần factory cho từng class.
        ShippingCalculator calculator =
                new ShippingCalculator(20_000, 200_000);
        InvoiceJournal journal = new ConsoleInvoiceJournal();
        Clock clock = Clock.systemUTC();

        InvoiceService service =
                new InvoiceService(calculator, journal, clock);
        service.issue("INV-001", 150_000);
        service.issue("INV-002", 200_000);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LeanDiDemo.java
java LeanDiDemo
~~~

Kết quả mong đợi:

~~~text
ISSUED INV-001: subtotal=150000, shipping=20000, total=170000
ISSUED INV-002: subtotal=200000, shipping=0, total=200000
~~~

### Tại sao không thêm interface cho `ShippingCalculator`?

- Thuật toán hiện tại là công thức thuần, không gọi mạng hay database.
- `ShippingCalculator` được cấu hình bằng hai số tại startup và không giữ trạng thái request mutable.
- Có thể **test class thật** nhanh chóng; không cần mock để tránh tác dụng phụ.
- `InvoiceService` vẫn không tự gọi `new ShippingCalculator`: composition root tạo và truyền nó.
- Khi phát sinh **nhiều chính sách thực sự độc lập**, ta có thể tách `ShippingPolicy` và chuyển tham số constructor sang hợp đồng đó khi có test bảo vệ.

Không có factory vì **không có phiên nào cần tạo lại cho từng đơn**. `Invoice` được tạo bằng `new` ngay trong use case vì nó là **kết quả nghiệp vụ**, không phải một dependency hạ tầng được giấu bên trong.

### Vì sao `InvoiceJournal` lại là interface?

`journal.save` là ranh giới tác dụng phụ. Test có thể cung cấp một fake ghi nhận lời gọi; production có thể dùng file, database hoặc queue. Interface này có một vai trò **thực tế**, ngay cả khi ứng dụng nhỏ hiện chỉ dùng một adapter trên console.

Tuy nhiên, interface cũng **không bắt buộc cho mọi bài toán I/O**. Trong một công cụ nhỏ chỉ ghi file một lần và được test bằng thư mục tạm, inject một lớp cụ thể vẫn có thể đủ. Quyết định nằm ở chi phí bảo vệ ranh giới và nhu cầu kiểm thử, không phải luật “hễ I/O là interface”.

## 7. Unit test không mock phép tính thuần túy

Hãy thử xác nhận cấu hình phí và use case bằng **calculator thật**; chỉ thay journal có tác dụng phụ bằng fake. Đây là một ví dụ rõ về việc **ít abstraction nhưng vẫn test tốt**.

Lưu thành **`LeanDiDemoTest.java`** cùng thư mục với chương trình:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public final class LeanDiDemoTest {

    static final class RecordingJournal
            implements LeanDiDemo.InvoiceJournal {
        final List<LeanDiDemo.Invoice> saved = new ArrayList<>();

        @Override
        public void save(LeanDiDemo.Invoice invoice) {
            saved.add(invoice);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectFailure(
            Class<? extends RuntimeException> expected, Runnable work) {
        try {
            work.run();
        } catch (RuntimeException failure) {
            if (expected.isInstance(failure)) {
                return;
            }
            throw new AssertionError("Sai loại ngoại lệ", failure);
        }
        throw new AssertionError("Không xảy ra ngoại lệ mong đợi");
    }

    public static void main(String[] args) {
        LeanDiDemo.ShippingCalculator realCalculator =
                new LeanDiDemo.ShippingCalculator(20_000, 200_000);

        check(realCalculator.feeFor(150_000) == 20_000,
                "Dưới ngưỡng phải chịu phí");
        check(realCalculator.feeFor(200_000) == 0,
                "Đúng ngưỡng phải miễn phí");
        check(realCalculator.feeFor(250_000) == 0,
                "Trên ngưỡng phải miễn phí");

        expectFailure(IllegalArgumentException.class,
                () -> new LeanDiDemo.ShippingCalculator(-1, 200_000));
        expectFailure(IllegalArgumentException.class,
                () -> realCalculator.feeFor(0));

        RecordingJournal journal = new RecordingJournal();
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);

        LeanDiDemo.InvoiceService service =
                new LeanDiDemo.InvoiceService(
                        realCalculator, journal, fixed);

        LeanDiDemo.Invoice first = service.issue("INV-001", 150_000);
        check(first.shippingFeeVnd() == 20_000, "Sai phí");
        check(first.totalVnd() == 170_000, "Sai tổng");
        check(first.createdAt().equals(
                Instant.parse("2026-01-01T00:00:00Z")),
                "Clock phải kiểm soát thời gian");
        check(journal.saved.size() == 1
                && journal.saved.get(0) == first,
                "Journal phải nhận đúng kết quả");

        LeanDiDemo.Invoice second = service.issue("INV-002", 200_000);
        check(second.shippingFeeVnd() == 0, "Sai ngưỡng miễn phí");
        check(journal.saved.size() == 2, "Phải lưu hai hóa đơn");

        expectFailure(IllegalArgumentException.class,
                () -> service.issue("sai mã", 10_000));
        expectFailure(IllegalArgumentException.class,
                () -> service.issue("INV-003", 0));
        check(journal.saved.size() == 2,
                "Dữ liệu không hợp lệ không được lưu");

        // Bảo vệ tràn số trước khi gọi adapter.
        LeanDiDemo.InvoiceService hugeService =
                new LeanDiDemo.InvoiceService(
                        new LeanDiDemo.ShippingCalculator(
                                20_000, Long.MAX_VALUE),
                        journal,
                        fixed);
        expectFailure(ArithmeticException.class,
                () -> hugeService.issue("INV-004", Long.MAX_VALUE - 1));
        check(journal.saved.size() == 2,
                "Tràn số không được gây tác dụng phụ");

        expectFailure(NullPointerException.class,
                () -> new LeanDiDemo.InvoiceService(
                        null, journal, fixed));

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac LeanDiDemo.java LeanDiDemoTest.java
java LeanDiDemoTest
~~~

Bài test không cần Spring, annotation, test container, mocking framework hoặc file thật. `ShippingCalculator` là hiện thực cụ thể nhưng vẫn được tiêm và kiểm thử trực tiếp. `Clock.fixed` giúp thời gian tất định. `RecordingJournal` cô lập tác dụng phụ, vì **đó là ranh giới cần thay thế trong test**.

Một test integration riêng vẫn cần thiết nếu sau này `InvoiceJournal` được hiện thực bằng database hoặc HTTP. Unit test với fake không tự chứng minh adapter thật mapping dữ liệu đúng.

## 8. Trước và sau khi loại bỏ abstraction thừa

Giả sử đội ngũ đang dùng một wrapper chain:

~~~mermaid
flowchart LR
    Root["Composition root"]
    FactoryInterface["IShippingCalculatorFactory"]
    FactoryImpl["ShippingCalculatorFactoryImpl"]
    CalcInterface["IShippingCalculator"]
    CalcImpl["ShippingCalculatorImpl"]
    Service["InvoiceService"]
    Root --> FactoryInterface
    FactoryInterface --> FactoryImpl
    FactoryImpl -->|"new"| CalcImpl
    CalcImpl -.-> CalcInterface
    Service --> CalcInterface
~~~

Nếu tất cả các lớp trên chỉ phục vụ **một công thức cố định**, graph này làm tăng chi phí tìm hiểu mà không thêm được khả năng vận hành có ý nghĩa.

Sau khi đơn giản:

~~~mermaid
flowchart LR
    Root["Composition root"]
    Calc["ShippingCalculator"]
    Service["InvoiceService"]
    Root -->|"new và constructor injection"| Service
    Root -->|"new"| Calc
    Service -->|"dùng"| Calc
~~~

Việc loại bỏ interface/factory không làm mất khả năng **tiêm phụ thuộc**. Khi nhu cầu xuất hiện, có thể bổ sung một seam đúng chỗ thay vì phải bảo trì mọi seam giả định từ ban đầu.

### So sánh chi phí thay đổi

| Thay đổi | Mô hình phức tạp không cần thiết | Mô hình gọn |
| --- | --- | --- |
| Đổi ngưỡng miễn phí | Có thể phải lần theo factory/bean binding | Thay config tại composition root |
| Thay chi tiết tính phí nhưng không đổi hợp đồng | Vẫn sửa implementation | Sửa class tính phí và test |
| Test `InvoiceService` | Có thể mock nhiều interface không cần thiết | Dùng calculator thật và fake journal |
| Thêm một chính sách tính phí thật sự khác | Phải tổ chức lại binding/chọn implementation | Thêm `ShippingPolicy` có mục đích và test |
| Cần tạo phiên ngắn hạn có state | Factory hiện tại có thể vẫn thiếu lifecycle rõ | Thêm factory chuyên biệt với hợp đồng ownership |

**Không có quy tắc mọi refactor phải làm giảm số class.** Nếu tính linh hoạt đang mang lại giá trị thực hoặc một API thư viện được nhiều module dùng độc lập, giữ abstraction có thể đúng. Điểm cần tránh là duy trì cấu trúc chỉ vì sợ thay đổi chưa có bằng chứng.

## 9. Khi nào một interface duy nhất vẫn đáng giữ?

Lỗi không nằm ở con số “một implementation”. Các trường hợp sau là lý do chính đáng dù chỉ có một adapter production:

**Bảo vệ ranh giới hạ tầng.** `PaymentGateway` chỉ có một nhà cung cấp thanh toán hiện tại, nhưng core cần tránh phụ thuộc SDK thanh toán. Fake test cần không charge thật.

**Định nghĩa giao kèo giữa module.** Một nhóm sở hữu module nghiệp vụ, nhóm khác sở hữu data adapter. Port đặt ở phía consumer giúp hai module thay đổi độc lập trong giới hạn hợp đồng.

**Giảm rủi ro kiểm thử tác dụng phụ.** Nếu test phải mở network/database hay chờ queue thật chỉ vì không có seam, một interface nhỏ có thể làm test nhanh hơn và đáng tin cậy hơn.

**Chính sách có khả năng biến động đã được xác nhận.** Sản phẩm đã có yêu cầu rõ về nhiều chiến lược giá, gửi thông báo hoặc điều phối tùy thị trường, dù hiện tại mới triển khai một chiến lược.

**Giới hạn phụ thuộc giữa thư viện hoặc runtime.** Một core được sử dụng cả ở CLI và web không nhất thiết phải import thư viện của framework web.

Với mỗi trường hợp, hãy hỏi **interface nằm ở phía nào**. Một port tốt thường mô tả nhu cầu consumer như `save(invoice)`, không sao chép toàn bộ API của repository vendor hoặc SDK.

### Không dùng interface làm “vé miễn phí” cho coupling

Giả sử:

~~~java
interface PaymentSdkWrapper {
    VendorPaymentResponse postVendorCharge(VendorPaymentRequest request);
}
~~~

Nếu core vẫn phải import hai kiểu `VendorPayment...`, việc thêm interface chưa thật sự cách ly chi tiết vendor. Một port có ý nghĩa nghiệp vụ hơn có thể nhận `orderId` và số tiền, rồi adapter chịu trách nhiệm mapping DTO vendor.

Interface có ích khi **định nghĩa ranh giới thay đổi**, không đơn thuần vì nó mang từ khóa `interface`.

## 10. Khi nào factory thực sự giải quyết vòng đời?

Một factory đáng giá hơn wrapper `new` khi nó giải quyết **thời điểm tạo, scope, tham số runtime hoặc ownership**.

Ví dụ mỗi lần xuất báo cáo cần mở một file khác, không thể tiêm một `BufferedWriter` duy nhất vào singleton `ReportService` rồi dùng cho tất cả báo cáo.

~~~java
// Phác họa hợp đồng; các kiểu còn lại được định nghĩa theo ứng dụng.
interface ExportSession extends AutoCloseable {
    void write(String line) throws java.io.IOException;

    @Override
    void close() throws java.io.IOException;
}

interface ExportSessionFactory {
    ExportSession open(String reportId) throws java.io.IOException;
}

final class ReportService {
    private final ExportSessionFactory sessions;

    ReportService(ExportSessionFactory sessions) {
        this.sessions = java.util.Objects.requireNonNull(
                sessions, "sessions");
    }

    void export(String reportId, String content)
            throws java.io.IOException {
        try (ExportSession session = sessions.open(reportId)) {
            session.write(content);
        }
    }
}
~~~

Ở đây factory có **trách nhiệm thật**:

- Nhận `reportId` chỉ biết khi thao tác bắt đầu.
- Mỗi lần `open()` cấp một session phù hợp.
- Bên gọi sở hữu sản phẩm được trả về và đóng bằng `try-with-resources`.
- Nếu `open()` thất bại sau khi tạo một phần tài nguyên nhưng chưa trả sản phẩm, factory phải tự dọn phần đã mở.
- Factory có thể giữ tham chiếu đến cấu hình hoặc tài nguyên dùng chung, nhưng không nên tự ý chuyển quyền đóng resource cấp ứng dụng cho từng report.

Factory này **không tương đương** `DefaultReceiptFormatterFactory.create()` trong ví dụ đầu, vì nó đưa ra một chính sách vòng đời mà constructor trực tiếp không thể biểu diễn bằng một instance duy nhất.

### Provider và lazy là nhu cầu khác factory tạo mỗi lần

Nếu chỉ muốn tạo một index nặng **ở lần truy cập đầu tiên rồi dùng lại**, một lazy provider có cache phù hợp hơn factory mặc định tạo mới mỗi lần. Nếu một singleton cần truy cập dependency theo scope request, provider phải phân giải trong scope hiện hành và **không** cho phép cache instance request thật trong singleton.

`Supplier<T>` là một API hàm, không tự bảo đảm semantics lazy, memoization hoặc tạo mới. Khi chọn một abstraction, phải mô tả hành vi thay vì suy đoán từ tên phương thức `get()`.

## 11. Tác động của overengineering đến object graph, scope và lỗi cấu hình

Abstraction không cần thiết không chỉ tạo thêm file mà còn tăng số mối nối phải kiểm soát:

- **Nhiều binding hơn:** interface có một implementation vẫn cần biết nơi đăng ký; thêm nhiều implementation tạo nguy cơ chọn nhầm, trùng hoặc thiếu binding.
- **Nhiều vòng đời mập mờ hơn:** factory/proxy vô nghĩa có thể khiến khó biết ai tạo, ai giữ và ai đóng sản phẩm.
- **Test giả tạo:** mock từng helper thuần túy khiến test kiểm tra “gọi đúng phương thức” thay vì kiểm tra kết quả nghiệp vụ.
- **Chi phí điều hướng:** phải nhảy giữa interface, factory, implementation và bean config để hiểu một phép tính.
- **Trì hoãn lỗi không cần thiết:** dùng lazy/provider cho dependency bắt buộc có thể dời lỗi cấu hình từ startup sang lần dùng đầu tiên.
- **Khó tách trách nhiệm:** service có thể tiếp tục vi phạm single responsibility dù mọi dependency đều có interface.

Tuy nhiên, xóa tất cả abstraction cũng gây rủi ro nếu mất một ranh giới bảo vệ hạ tầng. Mục tiêu là **đặt abstraction ở nơi có sự khác biệt thật**: biến thể thuật toán, tác dụng phụ, việc tạo theo scope hoặc interface giữa các module.

~~~mermaid
flowchart TD
    Need["Cần một dependency"]
    Need --> Different{"Có nhiều hành vi hoặc ranh giới cần bảo vệ?"}
    Different -->|"Có"| Port["Interface / port có mục đích"]
    Different -->|"Không"| Concrete["Tiêm lớp cụ thể hoặc dùng helper thuần"]
    Need --> Lifetime{"Mỗi lần dùng cần tạo mới/trì hoãn/quản lý resource?"}
    Lifetime -->|"Có"| Factory["Factory / provider theo hợp đồng vòng đời"]
    Lifetime -->|"Không"| Direct["Tạo tại composition root, inject trực tiếp"]
~~~

Hai câu hỏi trong sơ đồ **độc lập**: có thể cần interface nhưng không cần factory, hoặc cần factory tạo những đối tượng cụ thể mà không cần interface cho từng sản phẩm.

## 12. Quy trình refactor an toàn khi đã có quá nhiều interface/factory

Không nên xóa hàng loạt interface chỉ vì thấy một implementation. Hãy bảo đảm thay đổi không phá API công khai, ranh giới module hoặc các mục tiêu test trước đó.

1. **Lập bản đồ dependency.** Với mỗi interface/factory, xác định consumer, implementation, nơi tạo, scope và owner.
2. **Tìm lý do tồn tại.** Có nhiều chiến lược, port I/O, SDK, contract giữa module, runtime arguments, caching hay tài nguyên cần đóng không?
3. **Kiểm tra việc sử dụng thật.** Factory có được gọi mỗi request? Một sản phẩm có state cần riêng? Interface có được dùng trong integration hoặc plugin không?
4. **Xác định hành vi và test hiện tại.** Test các kết quả nghiệp vụ, điều kiện biên và đường lỗi; không chỉ test mock invocation.
5. **Đơn giản hóa seam vô ích trước.** Ví dụ bỏ factory chỉ gọi constructor rỗng, để composition root tự tạo concrete dependency.
6. **Chuyển consumer sang constructor phù hợp.** Khi bỏ interface, tiêm trực tiếp class cụ thể; kiểm tra `Objects.requireNonNull` cho dependency bắt buộc.
7. **Giữ port thực sự bảo vệ hạ tầng.** Nếu cần fake I/O và cách ly SDK, đừng xóa chỉ vì chỉ có một adapter.
8. **Kiểm tra lifecycle và scope.** Nếu factory cũ thực sự đóng/mở resource, cần chuyển trách nhiệm đó đến owner khác trước khi loại bỏ.
9. **Chạy unit test và test wiring/integration theo phạm vi.** Refactor cấu trúc không được âm thầm đổi semantics nghiệp vụ hoặc quyền sở hữu.
10. **Ghi lại tiêu chí bổ sung abstraction sau này.** Ví dụ khi có chiến lược thứ hai, khi cần task-scoped instance hoặc khi core phải tránh vendor API.

Đây là cách refactor **theo bằng chứng**, thay vì thiết kế sẵn mọi tầng abstraction rồi hy vọng tương lai cần tới.

## 13. Lỗi đánh giá thường gặp

| Ngộ nhận | Điều chính xác hơn |
| --- | --- |
| “DI bắt buộc inject interface.” | Concrete constructor injection vẫn là DI |
| “Một interface chỉ có một implementation luôn sai.” | Nó có thể là port I/O, seam test hoặc hợp đồng module |
| “Factory làm code luôn dễ test hơn.” | Factory không có trách nhiệm có thể chỉ tăng số lớp cần mock |
| “Mọi `new` trong ứng dụng đều vi phạm IoC.” | Tạo value object, collection và lắp ghép ở composition root là bình thường |
| “Dùng DI container thì phải có interface cho từng bean.” | Container có thể tạo và tiêm class cụ thể |
| “Muốn thay code sau này nên tạo sẵn mọi abstraction.” | Có thể refactor khi biến động thật xuất hiện và đã có test |
| “Một class bất biến cần factory để quản lý lifecycle.” | Nếu không có tài nguyên/state hoặc chính sách tạo, constructor đủ |
| “Tiêm một singleton tức là sai scope.” | Singleton dùng chung có thể đúng nếu không giữ request state và đủ thread-safe |
| “Có `Supplier` nghĩa là sẽ tạo mới mỗi lần.” | Hành vi do implementation của supplier quy định |
| “Mock toàn bộ dependency mới là unit test tốt.” | Dùng concrete thuần túy thật và fake đúng ranh giới thường cho test có giá trị hơn |
| “Thêm nhiều interface làm kiến trúc chắc chắn ít coupling.” | Coupling phụ thuộc chất lượng ranh giới, không phải số lượng interface |
| “Factory tự đóng mọi sản phẩm được cấp.” | Ownership phải được nêu rõ: caller, factory hay scope manager đóng? |

## 14. Checklist quyết định trước khi thêm abstraction

Trước khi tạo **interface**, hãy trả lời:

- Có ít nhất hai hành vi cần thay thế, hoặc một biến động đã được xác nhận không?
- Có ranh giới I/O, SDK, module hoặc test cần cô lập không?
- Hợp đồng có diễn đạt **nhu cầu của consumer** thay vì sao chép API của implementation không?
- Nếu dùng class cụ thể hôm nay, việc thay đổi sau này có thật sự tốn kém và rủi ro không?

Trước khi tạo **factory/provider**, hãy trả lời:

- Có cần tham số runtime chỉ biết ở từng tác vụ không?
- Có cần đối tượng mới theo request, session hoặc transaction không?
- Có quy tắc lazy, pool, cache, chọn hiện thực hoặc khởi tạo phức tạp không?
- Ai sở hữu/đóng sản phẩm? Nếu tạo dở dang thất bại, ai dọn?
- `new` tại composition root có đang đủ đơn giản, rõ ràng và đúng vòng đời không?

Trước khi chuyển sang **DI container**, hãy hỏi thêm: object graph, biến thể cấu hình và scope đã phức tạp đến mức container giảm đáng kể chi phí bảo trì chưa? Nếu chỉ có vài dependency và một composition root dễ đọc, **manual DI có thể đã đủ**.

## 15. Bài tập thực hành và tự đánh giá

**Bài 1 — Bỏ một factory vô nghĩa.** Cho `TaxCalculatorFactory.create()` luôn trả `new TaxCalculator(10)`, không có state riêng, I/O hoặc logic chọn. Hãy chuyển cách tạo về composition root, tiêm `TaxCalculator` trực tiếp và xác nhận test vẫn cho cùng kết quả.

**Bài 2 — Giữ interface hợp lý.** Một `OrderService` chỉ dùng một adapter JDBC để lưu dữ liệu, nhưng unit test đang phải mở database thật. Giải thích vì sao `OrderRepository` là một port có giá trị dù production mới có một implementation. Thiết kế fake cho test và adapter lưu bằng JDBC.

**Bài 3 — Tạo biến thể thật sự.** `ShippingCalculator` có thêm hai chiến lược doanh nghiệp độc lập: vận chuyển theo trọng lượng và theo khu vực. Hãy xác định khi nào đáng trích `ShippingPolicy`, những tham số nào hợp đồng cần, và nơi lựa chọn policy ở composition root.

**Bài 4 — Factory theo tác vụ.** Một `ReportService` cần mở file khác nhau mỗi request. Viết interface `ExportSessionFactory` và `ExportSession extends AutoCloseable`. Ai phải đóng phiên? Nếu mở file thứ hai thất bại sau khi mở file thứ nhất, ai giải phóng tài nguyên đã mở?

**Bài 5 — Thử không dùng mock.** Với `LeanDiDemo`, dùng `ShippingCalculator` thật, `Clock.fixed` và fake `InvoiceJournal` để kiểm tra ngưỡng miễn phí, tổng tiền, input sai và không có tác dụng phụ sau lỗi tràn số.

**Bài 6 — Vẽ lại object graph.** Một dự án có `UserService → UserValidatorInterface → UserValidatorImpl` và `UserValidatorFactoryImpl` chỉ gọi constructor. Vẽ graph trước/sau khi bỏ lớp thừa; nêu điều kiện nào khiến bạn **không** nên xóa abstraction đó.

**Bài 7 — Scope và concurrency.** Một factory trả lại cùng một builder mutable cho mọi request. Tên `create()` có bảo đảm sản phẩm mới không? Viết test hai request, chỉ ra rủi ro lẫn state và đề xuất hợp đồng factory mới nếu từng request cần instance riêng.

**Bài 8 — Lập luận trong code review.** Khi đồng nghiệp yêu cầu mọi service phải có interface “để theo SOLID”, hãy giải thích bằng ba nhóm ví dụ: (a) concrete helper thuần túy; (b) port I/O một implementation; (c) strategy có nhiều implementation. Với mỗi nhóm, đề xuất số abstraction tối thiểu có lý do.

**Kết luận:** Thiết kế DI tốt là thiết kế **công bố phụ thuộc cần thiết, đặt quyết định tạo ở đúng ranh giới và quản lý vòng đời có chủ đích**. Interface giúp bảo vệ ranh giới hoặc thay hành vi; factory giúp điều phối việc tạo và scope. Khi không có những nhu cầu ấy, tiêm một lớp cụ thể và lắp ghép bằng Java thuần thường rõ ràng, dễ kiểm thử và dễ bảo trì hơn một hệ thống nhiều lớp trung gian.
