# Lắp ghép ứng dụng Java bằng constructor và đối tượng thông thường

**Dependency Injection (DI) thủ công** là cách tạo các đối tượng Java bình thường rồi truyền những đối tượng mà chúng cần vào constructor hoặc phương thức, **không cần DI container**. Với cách làm này, nơi khởi động ứng dụng chủ động tạo và nối các thành phần; còn lớp thực hiện nghiệp vụ chỉ sử dụng các cộng tác viên được cung cấp.

Đây là bước nền tảng để hiểu **Inversion of Control (IoC)** trong việc lắp ghép đối tượng: lớp nghiệp vụ không tự chọn và tạo hạ tầng mà nó dùng. Khi đã nắm cách làm bằng Java thuần, ta mới có cơ sở đánh giá khi nào một container như Spring hoặc Guice thực sự giúp giảm công việc cấu hình.

Bài học thuộc phần **DI thủ công** của module Dependency Injection, tập trung vào một chương trình có thể chạy được, cách đọc sơ đồ phụ thuộc, cách viết composition root và cách kiểm thử mà không phải dựng framework.

## 1. Một object graph xuất hiện như thế nào?

Giả sử cần viết tính năng báo giá cho một mã sản phẩm và số lượng khách muốn mua.

- `QuoteHandler` nhận dữ liệu từ bên gọi và chuyển tới logic báo giá.
- `QuoteService` điều phối thao tác báo giá.
- `ProductCatalog` cung cấp thông tin sản phẩm.
- `PricingPolicy` tính tổng tiền dựa trên sản phẩm và số lượng.

`QuoteService` **dùng** `ProductCatalog` và `PricingPolicy`, nhưng **không cần biết tạo chúng bằng cách nào**. Các đối tượng và các quan hệ tham chiếu giữa chúng tạo thành **object graph**.

```text
  main() — composition root
    │
    ├── tạo InMemoryProductCatalog ───────┐
    │                                     │
    ├── tạo RegularPricingPolicy ─────────┤
    │                                     ▼
    ├── new QuoteService(catalog, pricing)
    │                 │
    │                 ▼
    └── new QuoteHandler(quoteService)
                      │
                      ▼
              handle("JAVA-BOOK", 2)
                      │
                      ▼
                QuoteService.quote(request)
                      ├── ProductCatalog.findBySku(...)
                      └── PricingPolicy.total(...)
```

Trong sơ đồ, `main()` là **composition root**: nơi tập trung quyết định dùng implementation nào và lắp đối tượng nào vào đối tượng nào. Nó tạo những nút nằm sâu trong graph trước, sau đó tạo các nút phụ thuộc vào chúng. Sau khi lắp xong, đường gọi nghiệp vụ đi qua graph đã có.

Có hai thời điểm cần phân biệt:

| Thời điểm | Ai quyết định? | Việc diễn ra |
|---|---|---|
| **Composition** | `main()` hoặc module cấu hình tại điểm khởi động | Chọn implementation, tạo đối tượng, truyền dependency qua constructor |
| **Execution** | Caller của use case | Gọi `handle` hoặc `quote` với dữ liệu riêng cho yêu cầu hiện tại |

DI thủ công có thể chỉ cần vài câu lệnh `new`. Từ “injection” ở đây không yêu cầu annotation, reflection, XML hoặc framework.

## 2. Nhận diện vấn đề trước khi lắp ghép

Một thiết kế ban đầu thường để service tự tạo những thứ nó cần:

```java
final class QuoteService {
    private final ProductCatalog catalog =
            new InMemoryProductCatalog(/* data */);
    private final PricingPolicy pricing = new RegularPricingPolicy();

    // Các phương thức nghiệp vụ...
}
```

*Đây là mã phác họa để thấy quan hệ thiết kế, không phải ví dụ độc lập biên dịch được.*

Cách này cố định lựa chọn hạ tầng bên trong `QuoteService`. Khi cần chuyển sang catalog đọc database, áp dụng bảng giá khác hoặc kiểm thử bằng fake, ta phải chỉnh sửa service hoặc tạo thêm đường vòng. Lớp nghiệp vụ đang đồng thời làm hai việc: **chọn/tạo cộng tác viên** và **sử dụng cộng tác viên**.

Với constructor injection, service khai báo trực tiếp những thành phần bắt buộc:

```java
final class QuoteService {
    private final ProductCatalog catalog;
    private final PricingPolicy pricing;

    QuoteService(ProductCatalog catalog, PricingPolicy pricing) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
        this.pricing = Objects.requireNonNull(pricing, "pricing");
    }

    // Các phương thức nghiệp vụ...
}
```

Bây giờ nơi gọi constructor chịu trách nhiệm cấp cả hai cộng tác viên. `QuoteService` chỉ biết các hợp đồng `ProductCatalog` và `PricingPolicy`; nó không cần biết implementation là in-memory, JDBC hay API bên ngoài.

**Lưu ý:** việc dùng interface giúp đổi implementation dễ hơn, nhưng không phải điều kiện bắt buộc của DI. Một constructor nhận thẳng lớp cụ thể vẫn là constructor injection. Hãy tạo abstraction khi nó thể hiện ranh giới hoặc nhiều cách thực hiện có ý nghĩa, thay vì sinh một interface cho mọi lớp.

## 3. Ví dụ Java thuần hoàn chỉnh

Ví dụ dùng Java 17 trở lên. Lưu **toàn bộ** đoạn mã dưới đây vào `ManualDiDemo.java` trong một thư mục trống.

```java
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class ManualDiDemo {

    // Dữ liệu nghiệp vụ.
    record Product(String sku, long unitPriceVnd) {
        Product {
            requireText(sku, "sku");
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd must be nonnegative");
            }
        }
    }

    record QuoteRequest(String sku, int quantity) {
        QuoteRequest {
            requireText(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
        }
    }

    record Quote(String sku, int quantity, long totalVnd) {}

    // Hợp đồng của các cộng tác viên.
    @FunctionalInterface
    interface ProductCatalog {
        Optional<Product> findBySku(String sku);
    }

    @FunctionalInterface
    interface PricingPolicy {
        long total(Product product, int quantity);
    }

    // Implementation hạ tầng đơn giản cho ví dụ.
    static final class InMemoryProductCatalog implements ProductCatalog {
        private final Map<String, Product> products;

        InMemoryProductCatalog(Map<String, Product> products) {
            this.products = Map.copyOf(
                    Objects.requireNonNull(products, "products"));
        }

        @Override
        public Optional<Product> findBySku(String sku) {
            return Optional.ofNullable(products.get(sku));
        }
    }

    // Chính sách giá riêng, không cần biết catalog được tạo ra sao.
    static final class RegularPricingPolicy implements PricingPolicy {
        @Override
        public long total(Product product, int quantity) {
            return Math.multiplyExact(product.unitPriceVnd(), quantity);
        }
    }

    // Use case nhận cộng tác viên qua constructor.
    static final class QuoteService {
        private final ProductCatalog catalog;
        private final PricingPolicy pricing;

        QuoteService(ProductCatalog catalog, PricingPolicy pricing) {
            this.catalog = Objects.requireNonNull(catalog, "catalog");
            this.pricing = Objects.requireNonNull(pricing, "pricing");
        }

        Quote quote(QuoteRequest request) {
            Objects.requireNonNull(request, "request");

            Product product = catalog.findBySku(request.sku())
                    .orElseThrow(() -> new IllegalArgumentException(
                            "Unknown SKU: " + request.sku()));

            long amount = pricing.total(product, request.quantity());
            return new Quote(product.sku(), request.quantity(), amount);
        }
    }

    // Lớp ở biên vào: chuyển input thành lời gọi use case.
    static final class QuoteHandler {
        private final QuoteService quotes;

        QuoteHandler(QuoteService quotes) {
            this.quotes = Objects.requireNonNull(quotes, "quotes");
        }

        String handle(String sku, int quantity) {
            Quote result = quotes.quote(new QuoteRequest(sku, quantity));
            return "QUOTE sku=" + result.sku()
                    + " qty=" + result.quantity()
                    + " total=" + result.totalVnd() + " VND";
        }
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
        return value;
    }

    public static void main(String[] args) {
        // 1. Tạo các thành phần lá: chưa phụ thuộc QuoteService.
        ProductCatalog catalog = new InMemoryProductCatalog(
                Map.of("JAVA-BOOK",
                        new Product("JAVA-BOOK", 120_000L)));
        PricingPolicy pricing = new RegularPricingPolicy();

        // 2. Lắp thành phần nghiệp vụ từ các cộng tác viên đã tạo.
        QuoteService quotes = new QuoteService(catalog, pricing);

        // 3. Lắp thành phần hướng vào người dùng.
        QuoteHandler handler = new QuoteHandler(quotes);

        // 4. Chạy nghiệp vụ với dữ liệu của một lần gọi.
        System.out.println(handler.handle("JAVA-BOOK", 2));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ManualDiDemo.java
java ManualDiDemo
```

Kết quả dự kiến:

```text
QUOTE sku=JAVA-BOOK qty=2 total=240000 VND
```

Ở ví dụ này, tiền được biểu diễn bằng `long` theo đơn vị VND nguyên, phù hợp cho bài tập tính số nguyên. `Math.multiplyExact` báo lỗi nếu phép nhân vượt phạm vi `long`; hệ thống tiền tệ thực tế cần chính sách về đơn vị nhỏ nhất, làm tròn, thuế và kiểu số phù hợp với miền nghiệp vụ.

### Đọc phần composition root

Toàn bộ mã lắp ghép nằm trong `main()`:

```java
ProductCatalog catalog = new InMemoryProductCatalog(
        Map.of("JAVA-BOOK", new Product("JAVA-BOOK", 120_000L)));
PricingPolicy pricing = new RegularPricingPolicy();
QuoteService quotes = new QuoteService(catalog, pricing);
QuoteHandler handler = new QuoteHandler(quotes);
```

Điểm đáng chú ý không phải số lượng lệnh `new` ít hay nhiều, mà là **vị trí thực hiện việc chọn implementation**. `QuoteService` chỉ xử lý yêu cầu báo giá; `QuoteHandler` chỉ nhận và chuyển input; `main` biết implementation cụ thể và lắp chúng lại.

Các đối tượng `Product`, `QuoteRequest` và `Quote` là **dữ liệu**, nên việc dùng `new` để tạo chúng trong logic xử lý không trái với DI. Mục tiêu là tách việc **chọn và khởi tạo cộng tác viên có trách nhiệm riêng**, không phải loại bỏ tất cả lệnh `new` khỏi toàn ứng dụng.

### Đọc phần constructor

`QuoteService` khai báo hai dependency cần thiết và kiểm tra `null` ngay khi khởi tạo:

```java
QuoteService(ProductCatalog catalog, PricingPolicy pricing) {
    this.catalog = Objects.requireNonNull(catalog, "catalog");
    this.pricing = Objects.requireNonNull(pricing, "pricing");
}
```

Nếu caller quên cấp một dependency, lỗi được phát hiện tại điểm tạo service. Constructor không truy vấn catalog, không tính báo giá và không tự mở kết nối. Điều này làm cho việc tạo object graph dễ suy luận hơn; còn việc sử dụng hạ tầng diễn ra khi caller gọi nghiệp vụ.

### Đọc phần dữ liệu mỗi lần gọi

`QuoteRequest` mô tả điều người dùng muốn báo giá **lần này**. Nó được tạo trong `handle(...)` và đi tiếp vào `quote(...)`. Không có field `currentSku` hoặc `currentQuantity` trong `QuoteService`.

Cùng một `QuoteService` có thể phục vụ nhiều yêu cầu mà không cần thay dependency trong constructor:

```java
System.out.println(handler.handle("JAVA-BOOK", 1));
System.out.println(handler.handle("JAVA-BOOK", 3));
```

Nếu gọi thêm hai dòng trên trong `main` của ví dụ, số lượng và kết quả thay đổi theo từng lần gọi, còn catalog và chính sách giá vẫn là các đối tượng đã lắp ghép ban đầu.

## 4. Tạo graph theo đúng thứ tự phụ thuộc

Khi tự lắp ghép, hãy bắt đầu từ những **đối tượng lá** rồi đi lên phía nhận request.

| Thành phần | Cần những gì khi tạo | Thời điểm có thể tạo |
|---|---|---|
| `InMemoryProductCatalog` | Dữ liệu sản phẩm | Đầu tiên |
| `RegularPricingPolicy` | Không có collaborator bắt buộc | Đầu tiên |
| `QuoteService` | `ProductCatalog` và `PricingPolicy` | Sau khi có hai collaborator |
| `QuoteHandler` | `QuoteService` | Sau khi có service |
| Lời gọi `handle(...)` | `QuoteHandler` và input mỗi yêu cầu | Sau khi graph đã lắp xong |

Thứ tự khai báo trong file không quan trọng bằng **thứ tự tạo instance lúc chạy**. Java sẽ yêu cầu caller truyền đúng số lượng và kiểu đối số khi gọi constructor; nếu graph lớn hơn, ta phải đảm bảo mọi dependency cần thiết đã được tạo và chọn đúng scope.

Một vòng phụ thuộc như `A` cần `B` trong constructor và `B` lại cần `A` sẽ làm việc lắp ghép trực tiếp trở nên bất khả thi với hai constructor đó, vì không thể tạo xong đối tượng nào trước. Đây thường là dấu hiệu nên xem lại ranh giới trách nhiệm hoặc tách hợp đồng, thay vì cố thêm global registry để giấu chu trình.

Khi ứng dụng có nhiều entry point (HTTP server, command-line tool, background worker), mỗi entry point có thể có composition root riêng hoặc gọi chung một hàm cấu hình được kiểm soát. Chúng không cần dùng cùng một đối tượng toàn cục.

## 5. Đổi implementation bằng cách thay lệnh lắp ghép

Giả sử khách được hưởng giảm giá cố định 10% và ta muốn đổi chính sách mà **không sửa `QuoteService`**. Có thể viết implementation khác:

```java
static final class TenPercentDiscount implements PricingPolicy {
    @Override
    public long total(Product product, int quantity) {
        long subtotal = Math.multiplyExact(
                product.unitPriceVnd(), quantity);
        return subtotal - subtotal / 10;
    }
}
```

Đây là ví dụ một class **đặt trong `ManualDiDemo`** để dùng được các kiểu lồng nhau của bài. Muốn bật nó, tại composition root thay:

```java
PricingPolicy pricing = new RegularPricingPolicy();
```

bằng:

```java
PricingPolicy pricing = new TenPercentDiscount();
```

Với sản phẩm giá 120.000 VND, số lượng 2, kết quả của chính sách giảm 10% là 216.000 VND. `QuoteService` vẫn phụ thuộc vào hợp đồng `PricingPolicy` và không cần biết logic tính tiền cụ thể.

Thay đổi ở **điểm lắp ghép** là một phần quan trọng của IoC trong thiết kế này: ứng dụng chọn chính sách, còn use case sử dụng chính sách đã được cung cấp. Sau này một DI container có thể đảm nhiệm việc chọn implementation, nhưng ranh giới giữa lựa chọn và sử dụng vẫn như vậy.

## 6. Kiểm thử bằng Java thuần: dùng fake thay vì infrastructure thật

Trong kiểm thử đơn vị, ta muốn kiểm tra `QuoteService` điều phối đúng catalog và chính sách giá. Vì dependency đi qua constructor, test có thể cấp fake riêng mà không dựng database hoặc container.

Lưu đoạn sau vào `ManualDiDemoCheck.java`, cùng thư mục với `ManualDiDemo.java`:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public final class ManualDiDemoCheck {
    public static void main(String[] args) {
        AtomicInteger catalogCalls = new AtomicInteger();
        AtomicInteger pricingCalls = new AtomicInteger();

        // Fake catalog: chỉ có một SKU đã biết.
        ManualDiDemo.ProductCatalog fakeCatalog = sku -> {
            catalogCalls.incrementAndGet();
            if (!"TEST-SKU".equals(sku)) {
                return Optional.empty();
            }
            return Optional.of(
                    new ManualDiDemo.Product("TEST-SKU", 10_000L));
        };

        // Fake pricing: trả giá có điều chỉnh để nhận ra service đã gọi nó.
        ManualDiDemo.PricingPolicy fakePricing = (product, quantity) -> {
            pricingCalls.incrementAndGet();
            return product.unitPriceVnd() * quantity - 1_000L;
        };

        var service = new ManualDiDemo.QuoteService(
                fakeCatalog, fakePricing);

        // Dữ liệu của một lần gọi do test cung cấp.
        var quote = service.quote(
                new ManualDiDemo.QuoteRequest("TEST-SKU", 2));

        if (!"TEST-SKU".equals(quote.sku())
                || quote.quantity() != 2
                || quote.totalVnd() != 19_000L) {
            throw new AssertionError("Wrong quote");
        }
        if (catalogCalls.get() != 1 || pricingCalls.get() != 1) {
            throw new AssertionError("Dependencies not called once");
        }

        // Trường hợp catalog không có sản phẩm.
        boolean rejected = false;
        try {
            service.quote(
                    new ManualDiDemo.QuoteRequest("MISSING", 1));
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        if (!rejected) {
            throw new AssertionError("Missing SKU should be rejected");
        }
        if (pricingCalls.get() != 1) {
            throw new AssertionError(
                    "Pricing must not run for missing SKU");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ManualDiDemo.java ManualDiDemoCheck.java
java ManualDiDemoCheck
```

Kết quả dự kiến: `PASS`.

Test đã chứng minh ba điều có giá trị thiết kế:

1. `QuoteService` dùng đúng `ProductCatalog` và `PricingPolicy` mà caller đã inject.
2. Dữ liệu `sku` và `quantity` của từng lần gọi được chuyển qua object graph tới collaborator phù hợp.
3. Khi catalog không tìm thấy sản phẩm, chính sách giá không được gọi. Use case kiểm soát thứ tự nghiệp vụ, còn fake khiến đường đi này quan sát được.

Dùng lambda làm fake ở đây thuận tiện vì mỗi interface chỉ có một phương thức trừu tượng. Với collaborator phức tạp hơn, có thể dùng class fake in-memory hoặc mock framework, nhưng **không cần framework để học DI**.

Một cảnh báo về mức độ bao phủ: đây là kiểm thử đơn vị cho đường điều phối, chưa kiểm tra tích hợp với database hay toàn bộ quy tắc giá sản phẩm thực tế. Khi thay collaborator bằng fake, những khác biệt giữa fake và infrastructure thật cần được kiểm tra ở tầng tích hợp riêng.

## 7. Lắp ghép thủ công và Dependency Inversion Principle

DI thủ công khuyến khích phụ thuộc qua abstraction có ý nghĩa nhưng không tự động bảo đảm một kiến trúc tốt.

Trong ví dụ:

- `QuoteService` là lớp thực hiện use case, chỉ biết `ProductCatalog` và `PricingPolicy`.
- `InMemoryProductCatalog` là chi tiết lưu trữ; `RegularPricingPolicy` là một chính sách cụ thể.
- `main` biết cả abstraction và implementation để tạo object graph.

Có thể mô tả hướng phụ thuộc mã nguồn và hướng cấp đối tượng:

```text
Hướng sử dụng khi chạy:
  QuoteService ── gọi ──► ProductCatalog implementation

Hướng phụ thuộc vào kiểu ở mã nguồn:
  QuoteService ── khai báo ──► ProductCatalog (abstraction)
  InMemoryProductCatalog ── implements ──► ProductCatalog

Hướng lắp ghép:
  main ── new InMemoryProductCatalog(...)
       └─ new QuoteService(catalog, pricing)
```

Điều này gần với **Dependency Inversion Principle (DIP)**: policy cấp cao không cần phụ thuộc trực tiếp vào chi tiết lưu trữ cấp thấp, và hai phía có thể gặp nhau ở hợp đồng phù hợp với nhu cầu nghiệp vụ. Tuy nhiên, **DIP** là nguyên lý định hướng quan hệ giữa các module; **DI** là kỹ thuật đưa object vào nơi sử dụng; **IoC** là ý tưởng rộng hơn về quyền kiểm soát. Ba khái niệm hỗ trợ nhau nhưng không đồng nghĩa.

Ví dụ vẫn thực hiện được DI nếu `QuoteService` nhận trực tiếp `InMemoryProductCatalog` qua constructor; chỉ là khả năng thay implementation và độ tách biệt giữa nghiệp vụ với chi tiết sẽ khác.

## 8. Quản lý scope và vòng đời khi không có container

Không có container không đồng nghĩa phải tạo lại mọi collaborator theo từng request. Người viết composition root cần tự quyết định đối tượng nào **dùng chung được an toàn** và đối tượng nào phải được **tạo, sử dụng, đóng** theo một scope ngắn hơn.

Trong ví dụ chính, `InMemoryProductCatalog` giữ map bất biến và `RegularPricingPolicy` không có trạng thái thay đổi. Với implementation cụ thể này, chia sẻ chúng qua nhiều lời gọi `quote(...)` là hợp lý. Nhưng đây là nhận xét về hai implementation đó, không phải quy tắc “mọi repository/policy đều singleton”.

| Trường hợp | Cách lắp ghép thường hợp lý | Lưu ý |
|---|---|---|
| Service bất biến, thread-safe, không lưu request hiện tại | Tạo một lần và dùng lại | Kiểm tra cả collaborator có an toàn khi dùng đồng thời không |
| Dữ liệu của từng yêu cầu, như `QuoteRequest` | Tạo/truyền khi gọi phương thức | Không giữ thành field của service dùng chung |
| Kết nối hoặc transaction có vòng đời ngắn | Cấp khi xử lý, đóng trong scope tương ứng | Tránh inject một connection ngắn hạn vào singleton dùng lâu |
| Pool hoặc client được ứng dụng sở hữu | Khởi tạo tại startup, chia sẻ theo hợp đồng, đóng khi shutdown | Ai tạo/chịu ownership phải rõ ràng |
| Hành vi được chọn theo tình huống runtime | Inject factory/selector hoặc truyền strategy theo lời gọi | Tránh trao cho service một registry tổng quát nếu không cần |

Ví dụ một collaborator là factory cho tài nguyên sống trong từng thao tác:

```java
interface UnitOfWork extends AutoCloseable {
    void save(String orderId);

    @Override
    void close();
}

interface UnitOfWorkFactory {
    UnitOfWork open();
}

final class OrderWriter {
    private final UnitOfWorkFactory units;

    OrderWriter(UnitOfWorkFactory units) {
        this.units = Objects.requireNonNull(units);
    }

    void write(String orderId) {
        try (UnitOfWork unit = units.open()) {
            unit.save(orderId);
        }
    }
}
```

Đoạn này **minh họa một thiết kế riêng**, giả định có import `java.util.Objects` và implementation hạ tầng. `OrderWriter` nhận `UnitOfWorkFactory` ở constructor; mỗi lần `write` mới tạo một `UnitOfWork` và đóng nó bằng `try-with-resources`. Cách commit/rollback khi thực hiện giao dịch thật cần hợp đồng riêng, không nên suy ra chỉ từ `close()`.

Nếu một factory tự mở tài nguyên rồi thất bại trước khi trả đối tượng, factory phải dọn những phần đã cấp phát dở. Nếu container hoặc pool quản lý tài nguyên dùng chung, service không tự ý đóng tài nguyên sau mỗi lần gọi. **Vòng đời và quyền sở hữu** là quyết định thiết kế phải rõ ngay cả khi lắp ghép bằng tay.

## 9. Ranh giới của composition root

Composition root không nhất thiết là một `main` dài hàng nghìn dòng. Khi graph lớn, có thể tách thành vài hàm hoặc class lắp ghép tập trung:

```java
final class ApplicationFactory {
    static QuoteHandler createQuoteHandler() {
        ProductCatalog catalog = createCatalog();
        PricingPolicy pricing = new RegularPricingPolicy();
        QuoteService service = new QuoteService(catalog, pricing);
        return new QuoteHandler(service);
    }

    private static ProductCatalog createCatalog() {
        // Chọn hạ tầng dựa trên cấu hình khởi động.
        return new InMemoryProductCatalog(/* products */);
    }
}
```

*Đây là phác thảo kiến trúc khi các kiểu đã được khai báo thích hợp, không phải file chạy độc lập.* Mục đích là giữ mã chọn implementation và lắp ghép ở một ranh giới dễ tìm. Trong một chương trình có nhiều module, composition root có thể gọi các hàm cấu hình hạ tầng, miễn là lớp nghiệp vụ không phải tự tra cứu những gì nó cần.

**Phân biệt với Service Locator:** nếu `QuoteService` gọi `GlobalRegistry.get(ProductCatalog.class)` trong `quote(...)`, nó đã chủ động tìm phụ thuộc. Truyền một đối tượng `ServiceLocator` vào constructor nhưng lại dùng locator để lấy mọi collaborator bên trong service cũng không làm hợp đồng phụ thuộc trở nên rõ ràng. Ngược lại, composition root có thể dùng API của một registry hoặc container để lấy collaborator **rồi truyền trực tiếp** vào constructor lớp nghiệp vụ.

Khi quyết định chỗ nào được tạo implementation, hãy hỏi: “Đây là đối tượng dữ liệu/phụ trợ nội bộ của một thao tác, hay là một cộng tác viên có chính sách, hạ tầng hoặc vòng đời cần được lựa chọn bên ngoài?” Chỉ nhóm sau mới là trọng tâm của việc tách công đoạn composition.

## 10. Các lỗi thường gặp khi DI thủ công

| Hiện tượng | Vì sao có vấn đề | Cách cải thiện |
|---|---|---|
| Service dùng `new JdbcRepository()` trong constructor hoặc mỗi method | Mã nghiệp vụ gắn trực tiếp với cách chọn hạ tầng | Tạo repository ở composition root rồi inject |
| Service gọi static `GlobalServices.get(...)` | Che collaborator thực tế và làm test phụ thuộc trạng thái toàn cục | Khai báo collaborator cần thiết trong constructor |
| Constructor có hàng chục dependency không liên quan | Có thể là dấu hiệu lớp ôm nhiều trách nhiệm | Xem lại use case và nhóm trách nhiệm; không giấu vấn đề bằng locator |
| Giữ `currentRequest` trong service dùng chung | Dữ liệu của lần gọi biến thành trạng thái chia sẻ | Truyền request qua tham số phương thức |
| Inject connection sống trong một request vào singleton | Phạm vi sử dụng có thể vượt vòng đời connection | Chọn scope phù hợp hoặc inject factory |
| Mở socket, gửi mail hay chạy nghiệp vụ trong constructor | Khởi tạo đối tượng bất ngờ gây I/O và side effect | Tách thành startup/lifecycle có chủ đích hoặc method |
| Tạo mọi đối tượng mới cho mỗi request mà không xét cost | Có thể tạo lại client, pool hoặc cache không cần thiết | Chia sẻ những thành phần thread-safe theo đúng ownership |
| Tạo interface cho mọi lớp vì “DI yêu cầu” | Làm tăng abstraction mà không có ranh giới rõ | Inject concrete type khi phù hợp; ưu tiên hợp đồng có ý nghĩa |
| Cố sửa circular dependency bằng global singleton | Che chu trình trách nhiệm giữa các lớp | Tách use case, hợp đồng hoặc luồng điều phối |

DI thủ công không tự làm hệ thống thread-safe. Nếu một collaborator giữ trạng thái mutable, cần có thiết kế đồng thời đúng; constructor injection đơn thuần không thay thế được khóa, thiết kế immutable hoặc giới hạn scope.

## 11. Khi nào chuyển sang DI container?

DI container thường giúp khi object graph lớn, việc chọn implementation phụ thuộc cấu hình, số lượng scope/lifecycle tăng hoặc ứng dụng đã dùng framework cung cấp các khả năng đó. Container có thể tự động giải quyết constructor dependency, cấu hình scope và gọi lifecycle hook. **Nó không tự quyết định ranh giới nghiệp vụ phù hợp**, và cũng không làm biến mất lỗi thiết kế do hidden dependency hoặc sai ownership.

| Câu hỏi | DI thủ công | Dùng DI container |
|---|---|---|
| Ai tạo graph? | Mã Java tại composition root | Container theo cấu hình và quy tắc đăng ký |
| Dependency được đưa vào service ra sao? | Constructor/method do caller gọi | Thường vẫn là constructor/method injection |
| Có cần annotation hoặc reflection? | Không | Tùy container và cách cấu hình |
| Mức độ nhìn thấy khi đọc code | Thấy rõ đường `new`, dễ debug graph nhỏ | Đường lắp ghép có thể phân tán ở metadata/config |
| Scope/lifecycle | Tự tổ chức bằng mã Java | Có thể được framework hỗ trợ nhưng vẫn cần hiểu và cấu hình đúng |
| Phù hợp nhất | Ứng dụng nhỏ, thư viện, bài học, graph không phức tạp | Ứng dụng lớn hoặc framework đã có hệ sinh thái DI |

**Không có ngưỡng số lớp cố định** buộc phải dùng container. Nếu graph thủ công còn dễ đọc, kiểm thử đơn giản và scope rõ ràng, giữ nó là lựa chọn hợp lý. Nếu mã lắp ghép lặp lại nhiều, quan hệ phụ thuộc khó quản lý và lifecycle phức tạp, container có thể giảm công việc thủ công.

## 12. Bài tập: tự mở rộng object graph

Bắt đầu từ `ManualDiDemo` và thử làm ba thay đổi sau, theo thứ tự.

**Bài tập 1 — Thêm một chính sách giá.** Viết `BulkPricingPolicy`: nếu `quantity >= 5` thì giảm 5% tổng tiền; còn lại giữ giá gốc. Thay duy nhất dòng tạo `PricingPolicy` trong `main()`. Xác nhận `QuoteService` không cần sửa.

**Bài tập 2 — Thêm catalog khác.** Tạo `StaticProductCatalog` trả về một sản phẩm cố định với SKU `"TRAINING"`, không dùng map. Đặt `ProductCatalog catalog = new StaticProductCatalog();` trong composition root, gọi handler với `"TRAINING"` và kiểm tra kết quả. Ý nghĩa là **thay cả nguồn dữ liệu qua cùng một interface**.

**Bài tập 3 — Kiểm thử lỗi đầu vào.** Viết chương trình `main` kiểm tra rằng `new QuoteRequest("", 1)` hoặc `new QuoteRequest("JAVA-BOOK", 0)` ném `IllegalArgumentException`. Giải thích vì sao việc validate dữ liệu request không cần truy vấn catalog ngay ở constructor của `QuoteService`.

### Gợi ý cho bài 1

Có thể viết class sau **bên trong `ManualDiDemo`**:

```java
static final class BulkPricingPolicy implements PricingPolicy {
    @Override
    public long total(Product product, int quantity) {
        long subtotal = Math.multiplyExact(
                product.unitPriceVnd(), quantity);
        return quantity >= 5
                ? subtotal - subtotal / 20
                : subtotal;
    }
}
```

Biểu thức `subtotal / 20` dùng phép chia số nguyên để tính chiết khấu 5%, nên có quy tắc cắt phần dư theo kiểu `long`. Bài tập này minh họa chính sách số nguyên, chưa phải mô hình làm tròn tiền tệ tổng quát. Quan sát xem việc đổi `RegularPricingPolicy` thành `BulkPricingPolicy` có đòi sửa `QuoteService` hay không; nếu không, ranh giới DI đã hoạt động như dự định.

### Câu hỏi tự kiểm tra

1. Nếu `QuoteService` tạo `new RegularPricingPolicy()` trong phương thức `quote(...)`, phần nào của IoC bị phá vỡ?
2. Nếu `main()` sử dụng `new InMemoryProductCatalog(...)`, chương trình có còn là DI không? Vì sao?
3. Vì sao `QuoteRequest` nên đi vào `quote(...)` thay vì bị giữ trong service dùng chung?
4. Có nên luôn tiêm `Clock`, `String` và `List` qua container? Những yếu tố nào quyết định?
5. Khi một `UnitOfWork` phải đóng sau mỗi request, có nên inject trực tiếp một instance `UnitOfWork` vào singleton service?

Gợi ý trả lời: (1) service lại tự chọn implementation chính sách; (2) vẫn là DI vì việc tạo collaborator nằm ở composition root; (3) request thay đổi theo mỗi lời gọi và không nên thành trạng thái chia sẻ; (4) xét vai trò, vòng đời, cấu hình và nhu cầu kiểm thử, không dựa vào kiểu dữ liệu; (5) thường không, cần tổ chức scope hoặc factory để tài nguyên tồn tại đúng một đơn vị công việc.

## Ghi nhớ

- **DI thủ công** dùng constructor và đối tượng Java bình thường để cấp collaborator từ bên ngoài; không cần thư viện hay container.
- **Composition root** chọn implementation, tạo đối tượng lá trước rồi lắp dần object graph đến thành phần nhận request.
- **Service nhận cộng tác viên; method nhận dữ liệu của từng lần gọi.** Việc tự tạo DTO hoặc giá trị kết quả không trái với DI.
- **Kiểm thử dễ hơn** vì test có thể đưa fake vào constructor và quan sát cách use case phối hợp các dependency.
- **Scope, vòng đời và ownership phải được thiết kế rõ** kể cả khi không dùng container. Khi graph và yêu cầu vận hành đủ phức tạp, DI container có thể hỗ trợ lắp ghép nhưng không thay thế được việc hiểu các ranh giới này.
