# Tính tường minh, khả năng điều hướng và chi phí lắp ghép

**Dependency Injection (DI)** giúp lớp nghiệp vụ nhận cộng tác viên từ bên ngoài thay vì tự tìm hoặc tự tạo chúng. Tuy nhiên, sau khi chuyển mã sang constructor injection, một nhóm phát triển vẫn cần quyết định **lắp graph bằng Java thuần, chia nhỏ thành các factory, hay giao việc đó cho DI container**.

Quyết định này không chỉ liên quan đến số dòng lệnh `new`. Nó có ít nhất ba mặt:

1. **Tính tường minh (explicitness):** nhìn vào lớp có biết nó cần những dependency nào không, và nhìn vào ranh giới khởi động có biết implementation nào được chọn không?
2. **Khả năng điều hướng (navigability):** khi đọc, review hoặc debug, có thể lần từ entry point đến service, binding và implementation thực tế nhanh đến đâu?
3. **Chi phí lắp ghép (composition cost):** phải viết, thay đổi, xác minh, khởi tạo và quản lý bao nhiêu mã/cấu hình để tạo ra object graph đúng?

Bài học thuộc chương **Đánh đổi thiết kế** của module Dependency Injection. Ta sẽ so sánh các lựa chọn bằng một use case Java 17, thực hành constructor injection và composition root bằng Java thuần, rồi xem khi nào một DI container đem lại lợi ích lớn hơn chi phí nhận thức của nó.

> **Không có lựa chọn luôn thắng.** Mã lắp ghép tường minh có thể dễ đọc nhưng dài khi graph lớn; container có thể giảm mã lặp nhưng phân tán thông tin lựa chọn implementation. Mục tiêu là làm rõ dependency, kiểm soát hành vi và giữ chi phí thay đổi phù hợp với quy mô ứng dụng.

## 1. Tường minh về *phụ thuộc* không đồng nghĩa tường minh về *lắp ghép*

Giả sử một lớp thực hiện đặt hàng:

```java
final class CheckoutService {
    private final Catalog catalog;
    private final PricePolicy pricing;
    private final ReceiptSink receipts;

    CheckoutService(
            Catalog catalog,
            PricePolicy pricing,
            ReceiptSink receipts) {
        this.catalog = Objects.requireNonNull(catalog);
        this.pricing = Objects.requireNonNull(pricing);
        this.receipts = Objects.requireNonNull(receipts);
    }
}
```

*Đây là trích đoạn cấu trúc; các kiểu đầy đủ nằm trong ví dụ ở mục 4.*

Chữ ký constructor cho biết **phụ thuộc trực tiếp** của `CheckoutService`. Đây là **tính tường minh ở lớp sử dụng**. Nhưng từ constructor, ta chưa biết:

- `Catalog` đang được triển khai bằng map, database hay HTTP client.
- `PricePolicy` là giá thường hay giảm giá.
- `ReceiptSink` có được chia sẻ với service khác không.
- Ba collaborator được tạo ở startup, mỗi request hay mỗi lần resolve.
- Ai chịu trách nhiệm đóng resource nếu một implementation có tài nguyên ngoài heap.

Những quyết định ấy thuộc về **composition**, có thể thể hiện bằng lệnh Java, factory module hoặc cấu hình container.

```text
Tường minh trong class:
  CheckoutService(Catalog, PricePolicy, ReceiptSink)
                  │          │              │
                  ▼          ▼              ▼
          Nhu cầu dùng các collaborator

Tường minh trong composition:
  InMemoryCatalog ───────────┐
  StandardPricePolicy ───────┼──► new CheckoutService(...)
  InMemoryReceiptSink ───────┘
```

Đừng đánh đồng hai mức này. Constructor injection giữ phần **nhu cầu sử dụng** dễ quan sát, ngay cả khi container quản lý phần **chọn và tạo**. Ngược lại, một composition root có hàng trăm lệnh `new` vẫn có thể đi cùng service dùng Service Locator và phụ thuộc ẩn; nhiều lệnh `new` tự thân không chứng minh DI đúng.

## 2. “Điều hướng được” là một thuộc tính của cả graph

Một lập trình viên thường phải trả lời các câu hỏi thực tế:

- Request HTTP hoặc lệnh CLI đi vào lớp nào?
- Lớp đang chạy được tạo ở đâu?
- Interface này được bind với implementation nào trong môi trường hiện tại?
- Nếu thêm một constructor parameter, phải sửa điểm lắp ghép nào?
- Khi lỗi xuất hiện, đường phụ thuộc nào dẫn tới implementation đó?
- Nếu client bị đóng sớm, ai là owner và nơi nào gọi `close()`?

Những câu hỏi đòi hỏi nhiều loại điều hướng:

| Loại điều hướng | Bắt đầu từ | Muốn tìm |
|---|---|---|
| **Dọc theo đường gọi** | Entry point | Use case và các collaborator được gọi khi xử lý |
| **Ngược tới nơi tạo** | Một service | Composition root, factory hoặc registration tạo ra nó |
| **Từ abstraction sang implementation** | Interface | Binding/qualifier và lớp cụ thể theo cấu hình |
| **Theo vòng đời** | Resource hoặc scope | Nơi tạo, nơi chia sẻ, nơi dừng và đóng |
| **Theo thay đổi** | Constructor hoặc contract | Những nơi cần cập nhật khi hợp đồng thay đổi |

Một IDE có thể tìm `new CheckoutService(...)` rất dễ nếu dự án dùng wiring Java trực tiếp. Với container, có thể phải tìm annotation, registration module, configuration class, bean factory hoặc generated source. Điều này **không có nghĩa container luôn khó debug**: framework có dependency graph report, diagnostics, validation và IDE plugin tốt có thể làm đường binding dễ quan sát hơn một tập factory viết tay phân tán.

**Khả năng điều hướng không tỷ lệ nghịch đơn giản với số file.** Một composition root 2.000 dòng không chia theo module cũng khó đọc; một graph được chia thành vài module factory có tên rõ và gọi từ một root duy nhất có thể dễ lần vết hơn.

## 3. Ba cách lắp cùng một object graph

Xét ứng dụng đặt hàng với các quan hệ sau:

```text
Main / Composition Root
    │
    ├── Catalog ─────────────────┐
    │                            │
    ├── PricePolicy ─────────────┤
    │                            ▼
    ├── ReceiptSink ────────► CheckoutService
    │                            │
    │                            ▼
    └──────────────────────► CheckoutHandler
                                 │
                                 ▼
                        handle(orderId, sku, qty)
```

Ba phương án có thể cùng tạo một graph về mặt hành vi.

### Phương án A — Wiring trực tiếp bằng Java

```java
Catalog catalog = new InMemoryCatalog(products);
PricePolicy pricing = new StandardPricePolicy();
ReceiptSink sink = new InMemoryReceiptSink();

CheckoutService service =
    new CheckoutService(catalog, pricing, sink);
CheckoutHandler handler = new CheckoutHandler(service);
```

**Lợi ích:** nhìn thấy thứ tự tạo, implementation và tham chiếu chia sẻ ngay tại root. Java compiler kiểm tra kiểu và chữ ký constructor.

**Chi phí:** khi ứng dụng có nhiều entry point hoặc hàng trăm registration, root có thể dài, lặp lại cách tạo instance và khó giữ đúng scope nếu tổ chức kém.

### Phương án B — Factory/module lắp ghép có tên rõ

```java
Catalog catalog = CatalogModule.create(settings);
PricePolicy pricing = PricingModule.create(settings);
CheckoutService service =
    CheckoutModule.create(catalog, pricing, sink);
```

*Các factory là pseudocode minh họa, không thuộc ví dụ chạy ở mục 4.*

**Lợi ích:** chia công việc cấu hình theo ranh giới module, tránh root trở thành file khổng lồ, trong khi luồng từ root tới module vẫn có thể điều hướng qua lời gọi Java.

**Chi phí:** nếu factory tự gọi registry toàn cục hoặc âm thầm tạo client khác, dependency và ownership có thể bị che. Không nên biến các module factory thành những tầng chuyển tiếp không có trách nhiệm riêng.

### Phương án C — Container đăng ký và phân giải

```text
register(Catalog, InMemoryCatalog)
register(PricePolicy, StandardPricePolicy)
register(ReceiptSink, InMemoryReceiptSink)
register(CheckoutService)
register(CheckoutHandler)

handler = container.resolve(CheckoutHandler)
```

*Đây là pseudocode có chủ đích: cú pháp, mặc định scope và validation khác nhau giữa các container.*

**Lợi ích:** giảm wiring lặp, có thể hỗ trợ scopes, qualifier, lifecycle, validation và tích hợp framework.

**Chi phí:** muốn biết `CheckoutService` đang nhận loại `PricePolicy` nào, có thể phải đi qua registration và profile/config. Lỗi thiếu binding có thể phát hiện ở build, startup hoặc lúc resolve tùy cơ chế và cách khởi tạo eager/lazy.

Cả ba phương án vẫn có thể là DI nếu business class **nhận collaborator qua constructor**. Một container không tự động tạo ra thiết kế tốt, và wiring thủ công không phải thiết kế sơ khai cần thay thế bằng mọi giá.

## 4. Ví dụ Java 17 hoàn chỉnh: graph tường minh, dễ lần dấu

Ví dụ cho phép chọn chính sách giá **thường** hoặc **giảm 10%** tại composition root. `CheckoutService` không tự đọc cấu hình hoặc tạo policy; handler chỉ biến dữ liệu từng lời gọi thành request. Một sink in-memory ghi lại biên bản đặt hàng để test quan sát side effect.

Lưu toàn bộ vào `ExplicitWiringDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class ExplicitWiringDemo {

    enum PricingMode {
        STANDARD, PROMO
    }

    record Product(String sku, long unitPriceVnd) {
        Product {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException(
                    "sku must not be blank");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
            }
        }
    }

    record CheckoutRequest(
            String orderId, String sku, int quantity) {
        CheckoutRequest {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                    "orderId must not be blank");
            }
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException(
                    "sku must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "quantity must be positive");
            }
        }
    }

    record Receipt(
            String orderId, String sku, int quantity,
            long totalVnd) {}

    @FunctionalInterface
    interface Catalog {
        Optional<Product> find(String sku);
    }

    @FunctionalInterface
    interface PricePolicy {
        long total(Product product, int quantity);
    }

    @FunctionalInterface
    interface ReceiptSink {
        void save(Receipt receipt);
    }

    static final class InMemoryCatalog implements Catalog {
        private final Map<String, Product> products;

        InMemoryCatalog(Map<String, Product> products) {
            this.products = Map.copyOf(
                Objects.requireNonNull(products, "products"));
        }

        @Override
        public Optional<Product> find(String sku) {
            return Optional.ofNullable(products.get(sku));
        }
    }

    static final class StandardPricePolicy
            implements PricePolicy {

        @Override
        public long total(Product product, int quantity) {
            return Math.multiplyExact(
                product.unitPriceVnd(), quantity);
        }
    }

    static final class PromoPricePolicy
            implements PricePolicy {

        @Override
        public long total(Product product, int quantity) {
            long subtotal = Math.multiplyExact(
                product.unitPriceVnd(), quantity);
            return subtotal - subtotal / 10;
        }
    }

    static final class InMemoryReceiptSink
            implements ReceiptSink {

        private final List<Receipt> saved = new ArrayList<>();

        @Override
        public void save(Receipt receipt) {
            saved.add(Objects.requireNonNull(receipt));
        }

        List<Receipt> snapshot() {
            return List.copyOf(saved);
        }
    }

    // Business service biết các contract, không biết concrete class.
    static final class CheckoutService {
        private final Catalog catalog;
        private final PricePolicy pricing;
        private final ReceiptSink receipts;

        CheckoutService(
                Catalog catalog,
                PricePolicy pricing,
                ReceiptSink receipts) {
            this.catalog = Objects.requireNonNull(
                catalog, "catalog");
            this.pricing = Objects.requireNonNull(
                pricing, "pricing");
            this.receipts = Objects.requireNonNull(
                receipts, "receipts");
        }

        Receipt checkout(CheckoutRequest request) {
            Objects.requireNonNull(request, "request");

            Product product = catalog.find(request.sku())
                .orElseThrow(() -> new IllegalArgumentException(
                    "Unknown SKU: " + request.sku()));

            long amount = pricing.total(
                product, request.quantity());

            Receipt receipt = new Receipt(
                request.orderId(),
                product.sku(),
                request.quantity(),
                amount);

            receipts.save(receipt);
            return receipt;
        }
    }

    // Entry point của ví dụ, không biết cách tạo các dependency.
    static final class CheckoutHandler {
        private final CheckoutService service;

        CheckoutHandler(CheckoutService service) {
            this.service = Objects.requireNonNull(
                service, "service");
        }

        String handle(String orderId, String sku, int quantity) {
            Receipt receipt = service.checkout(
                new CheckoutRequest(orderId, sku, quantity));

            return "ACCEPTED " + receipt.orderId()
                + " total=" + receipt.totalVnd() + " VND";
        }
    }

    // Graph object chỉ để demo quan sát kết quả tại composition root.
    record Graph(
            CheckoutHandler handler,
            InMemoryReceiptSink receiptSink) {}

    // Composition root: lựa chọn, tạo và nối instance.
    static Graph assemble(PricingMode mode) {
        Objects.requireNonNull(mode, "mode");

        Catalog catalog = new InMemoryCatalog(
            Map.of("BOOK", new Product("BOOK", 50_000L)));

        PricePolicy pricing = switch (mode) {
            case STANDARD -> new StandardPricePolicy();
            case PROMO -> new PromoPricePolicy();
        };

        InMemoryReceiptSink receipts =
            new InMemoryReceiptSink();

        CheckoutService checkout = new CheckoutService(
            catalog, pricing, receipts);

        CheckoutHandler handler =
            new CheckoutHandler(checkout);

        return new Graph(handler, receipts);
    }

    public static void main(String[] args) {
        Graph standard = assemble(PricingMode.STANDARD);
        System.out.println(
            standard.handler().handle(
                "ORDER-1", "BOOK", 2));
        System.out.println(
            "saved=" + standard.receiptSink().snapshot().size());

        Graph promo = assemble(PricingMode.PROMO);
        System.out.println(
            promo.handler().handle(
                "ORDER-2", "BOOK", 2));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ExplicitWiringDemo.java
java ExplicitWiringDemo
```

Kết quả dự kiến:

```text
ACCEPTED ORDER-1 total=100000 VND
saved=1
ACCEPTED ORDER-2 total=90000 VND
```

### Đọc code theo chiều từ root tới use case

Bắt đầu ở `main()`, gọi `assemble(PricingMode.STANDARD)`. Trong `assemble(...)`, ta biết ngay:

- Một `InMemoryCatalog` được tạo và chứa sản phẩm `BOOK`.
- `PricingMode` quyết định `StandardPricePolicy` hay `PromoPricePolicy`.
- Một `InMemoryReceiptSink` được cấp cho `CheckoutService`.
- `CheckoutHandler` nhận service đã tạo.
- `Graph` giữ handler và sink để demo kiểm tra side effect.

Không cần tra cứu toàn cục hoặc framework để biết graph. Nếu muốn đổi cách lưu biên bản sang database, phần lớn thay đổi nằm ở root và implementation của `ReceiptSink`; `CheckoutService.checkout(...)` vẫn gọi contract `save(...)`.

### Đọc code ngược từ consumer về composition

Đang debug `CheckoutService.checkout(...)`? Nhìn constructor để thấy ba collaborator. Sau đó tìm nơi gọi `new CheckoutService(...)` (IDE Find Usages). Với ví dụ này, kết quả dẫn thẳng tới `assemble(...)` và ba implementation cụ thể.

Đây là lợi thế của **đường lắp ghép tường minh**. Nhưng nó không miễn phí: khi graph có nhiều module, cần quy ước vị trí root/factory để người đọc không phải tìm giữa nhiều nơi tạo graph trùng lặp.

### Giới hạn của ví dụ

`InMemoryReceiptSink` dùng `ArrayList` và được chạy tuần tự. **Không mặc định chia sẻ nó giữa các request đa luồng** mà không có thiết kế đồng thời thích hợp.

`Graph` cố ý giữ concrete sink để test quan sát dữ liệu; production code có thể che sink phía sau API monitor hoặc đặt kiểm tra ở adapter. Việc container hoặc composition root **không** hiển thị hết nội bộ cho người dùng không làm DI mất tính tường minh, miễn ranh giới quản lý có thể được truy vết.

Giá được tính bằng `long` theo đơn vị VND nguyên. Phần giảm 10% sử dụng chia số nguyên và do đó có quy tắc cắt phần dư; hệ thống tiền tệ thật cần xác định quy tắc làm tròn, thuế và biểu diễn giá.

## 5. Kiểm thử: lợi thế của constructor rõ ràng không phụ thuộc container

Để chứng minh thiết kế vẫn kiểm thử bằng Java thuần, tạo `ExplicitWiringCheck.java` bên cạnh file demo:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class ExplicitWiringCheck {
    public static void main(String[] args) {
        // 1. Hai composition khác nhau chọn đúng policy.
        var standard = ExplicitWiringDemo.assemble(
            ExplicitWiringDemo.PricingMode.STANDARD);

        var promo = ExplicitWiringDemo.assemble(
            ExplicitWiringDemo.PricingMode.PROMO);

        String a = standard.handler().handle(
            "ORDER-A", "BOOK", 2);
        String b = promo.handler().handle(
            "ORDER-B", "BOOK", 2);

        if (!"ACCEPTED ORDER-A total=100000 VND".equals(a)
                || !"ACCEPTED ORDER-B total=90000 VND".equals(b)
                || standard.receiptSink().snapshot().size() != 1
                || promo.receiptSink().snapshot().size() != 1) {
            throw new AssertionError(
                "Composition selected an incorrect policy");
        }

        // 2. Test use case trực tiếp bằng fake, không cần graph thật.
        AtomicInteger catalogCalls = new AtomicInteger();
        AtomicInteger pricingCalls = new AtomicInteger();
        AtomicReference<ExplicitWiringDemo.Receipt> saved =
            new AtomicReference<>();

        ExplicitWiringDemo.Catalog catalog = sku -> {
            catalogCalls.incrementAndGet();
            return "TEST".equals(sku)
                ? Optional.of(new ExplicitWiringDemo.Product(
                    "TEST", 100L))
                : Optional.empty();
        };

        ExplicitWiringDemo.PricePolicy pricing =
            (product, quantity) -> {
                pricingCalls.incrementAndGet();
                return 777L;
            };

        ExplicitWiringDemo.ReceiptSink sink = saved::set;

        var service = new ExplicitWiringDemo.CheckoutService(
            catalog, pricing, sink);

        var receipt = service.checkout(
            new ExplicitWiringDemo.CheckoutRequest(
                "ORDER-C", "TEST", 3));

        if (receipt.totalVnd() != 777L
                || catalogCalls.get() != 1
                || pricingCalls.get() != 1
                || saved.get() != receipt) {
            throw new AssertionError(
                "Consumer did not use injected dependencies");
        }

        // 3. Không có SKU thì không tính giá hoặc ghi biên bản.
        boolean missingRejected = false;
        try {
            service.checkout(
                new ExplicitWiringDemo.CheckoutRequest(
                    "ORDER-D", "MISSING", 1));
        } catch (IllegalArgumentException expected) {
            missingRejected = true;
        }

        if (!missingRejected
                || catalogCalls.get() != 2
                || pricingCalls.get() != 1
                || saved.get() != receipt) {
            throw new AssertionError(
                "Unexpected behavior for unknown SKU");
        }

        // 4. Constructor từ chối thiếu collaborator bắt buộc.
        boolean nullRejected = false;
        try {
            new ExplicitWiringDemo.CheckoutService(
                null, pricing, sink);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }

        if (!nullRejected) {
            throw new AssertionError(
                "Missing constructor dependency was accepted");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ExplicitWiringDemo.java ExplicitWiringCheck.java
java ExplicitWiringCheck
```

Kết quả dự kiến: `PASS`.

Bốn nhóm khẳng định có mục đích khác nhau:

- **Composition test:** graph lựa chọn đúng policy theo mode.
- **Unit test consumer:** service thực sự dùng ba collaborator được inject.
- **Nhánh lỗi nghiệp vụ:** không tự gọi pricing hoặc lưu biên bản khi sản phẩm không tồn tại.
- **Bất biến constructor:** collaborator bắt buộc không được thiếu.

Không cần triển khai container chỉ để kiểm thử một service có constructor rõ ràng. Với hạ tầng thật, các phép thử trên vẫn cần được bổ sung bằng integration test, nhưng ranh giới unit test đã nhỏ và không phụ thuộc network.

## 6. Chi phí lắp ghép phải tính bằng nhiều trục

Khi cân nhắc manual wiring so với container, cụm từ “chi phí lắp ghép” thường bị thu hẹp vào **số dòng code khởi tạo**. Đó chỉ là một trục.

| Trục chi phí | Câu hỏi cần đo/quan sát |
|---|---|
| **Mã và cấu hình phải viết** | Có bao nhiêu factory, registration, qualifier, profile cần duy trì? |
| **Chi phí thay đổi** | Thêm một dependency vào constructor phải sửa bao nhiêu nơi? |
| **Khả năng truy vết** | Mất bao lâu để tìm đúng implementation cho một môi trường? |
| **Phát hiện lỗi** | Thiếu binding, nhầm scope, chu trình được báo lúc compile, build, startup hay request? |
| **Build/tooling** | Có annotation processing, code generation hay plugin IDE cần quản lý? |
| **Startup** | Bao nhiêu thời gian đọc cấu hình, scan metadata, build graph và mở tài nguyên? |
| **Runtime resolution** | Có tạo lại nhiều object/scope trong hot path không? |
| **Quản lý vòng đời** | Ai đóng pool, request resource và xử lý khi startup thất bại? |
| **Kiểm thử** | Test service có cần khởi động container hoặc server không? |
| **Chi phí học tập/điều tra lỗi** | Thành viên mới hiểu graph và thông báo lỗi ra sao? |

Một công thức tư duy định tính:

```text
Chi phí kỹ thuật tổng thể
  = chi phí tạo/cấu hình graph
  + chi phí bảo trì binding
  + chi phí quan sát và debug
  + chi phí validation và lifecycle
  + chi phí vận hành/build/runtime
```

Không nên diễn giải công thức như phép cộng các đại lượng có cùng đơn vị. Đây là danh sách các loại chi phí cần đánh giá, **không phải benchmark hiệu năng**.

### Chi phí máy và chi phí con người là hai chuyện khác nhau

Một container dùng reflection có thể tốn công khám phá constructor lúc runtime, nhưng tự động lắp graph và giảm mã bảo trì. Một công cụ sinh mã có thể đẩy một phần công việc sang build, giúp phát hiện một số lỗi sớm nhưng tăng độ phức tạp toolchain. Wiring thủ công có thể khởi động đơn giản hơn, nhưng một root quá lớn sẽ khiến review thay đổi vất vả.

Không có lý do để khẳng định **reflection luôn chậm**, **code generation luôn nhanh**, hoặc **ít dòng wiring luôn rẻ hơn**. Nếu phần lớn thời gian xử lý nằm ở database và network, chi phí lắp vài chục service có thể không đáng kể. Nếu ứng dụng khởi động liên tục và dựng graph rất lớn, startup cost có thể trở thành yêu cầu quan trọng.

Nên đo trên workload và cấu hình thực tế, tách thời gian đọc config, phân giải graph và khởi tạo tài nguyên khỏi thời gian thực hiện nghiệp vụ.

## 7. Chi phí thay đổi khi thêm một dependency

Giả sử sau này `CheckoutService` cần ghi audit khi lưu biên bản thành công. Constructor có thể đổi thành:

```java
CheckoutService(
    Catalog catalog,
    PricePolicy pricing,
    ReceiptSink receipts,
    AuditTrail audit)
```

*Đây là pseudocode về chữ ký mới; `AuditTrail` chưa được khai báo trong file ví dụ.*

Tác động phụ thuộc cách lắp ghép:

**Manual wiring:** mọi lời gọi `new CheckoutService(...)` cũ đều không khớp chữ ký và có thể bị Java compiler báo. Ta tới composition root, tạo/inject `AuditTrail`, rồi cập nhật test. **Lợi ích:** đường cần sửa hiển thị rõ. **Chi phí:** nhiều root hoặc factory trùng lặp sẽ cần cập nhật nhiều nơi.

**Factory module:** có thể chỉ cần sửa một `CheckoutModule.create(...)` nếu các root cùng gọi module đó. Nhưng nếu factory bí mật đọc `GlobalServices.get(...)`, việc thêm dependency có thể không hiện ra trong API của module, làm suy yếu tính tường minh.

**Container:** nếu `AuditTrail` đã đăng ký phù hợp, container có thể tự đưa vào constructor mà không sửa từng lời gọi `new`. Nếu chưa có binding, lỗi có thể được báo trong build/startup hoặc lúc bean được resolve, tùy framework. **Lợi ích:** giảm dây chuyền sửa mã cơ học. **Chi phí:** cần xác minh binding, scope và lựa chọn implementation thực tế.

Việc Java compiler báo thiếu constructor argument là một dạng **phản hồi sớm có giá trị**. Nhưng nó không xác nhận `AuditTrail` đã được cấu hình đúng môi trường, có quyền ghi hoặc đủ tài nguyên. Đây vẫn là trách nhiệm của phần composition/readiness và kiểm thử tích hợp.

## 8. Vì sao Service Locator có thể giảm wiring mà tăng chi phí điều hướng?

Giả sử service nhận một đối tượng registry rồi tự tìm phụ thuộc:

```java
// Pseudocode phản ví dụ: dependency thực tế bị giấu.
final class CheckoutService {
    private final ServiceRegistry registry;

    CheckoutService(ServiceRegistry registry) {
        this.registry = registry;
    }

    Receipt checkout(CheckoutRequest request) {
        Catalog catalog = registry.get(Catalog.class);
        PricePolicy pricing = registry.get(PricePolicy.class);
        ReceiptSink sink = registry.get(ReceiptSink.class);
        // ...
        return null;
    }
}
```

Nhìn constructor, ta chỉ thấy `ServiceRegistry`, không thấy ba collaborator thật. Tìm chỗ `new CheckoutService(registry)` cũng không chỉ ra implementation của catalog/pricing/sink. Test cần cấu hình registry hoặc thay bằng fake registry, thay vì cấp trực tiếp ba collaborator.

`Registry` có thể giúp thêm dependency mà không phải sửa constructor, nhưng đó **không hẳn là tiết kiệm tổng chi phí**. Nó chuyển một phần chi phí từ compiler và wiring sang:

- Đọc nội dung method để tìm những lệnh lookup.
- Phát hiện lỗi thiếu binding ở runtime.
- Theo dõi trạng thái global hoặc ambient context.
- Cấu hình test có nhiều trạng thái ngầm.
- Xác định scope của kết quả mỗi lần `get(...)`.

Một container vẫn có API `resolve/getBean`; dùng nó **tại composition root** rồi inject kết quả vào consumer là khác với việc phát container/registry rộng rãi cho các lớp nghiệp vụ. Một *factory có contract hẹp* như `UnitOfWorkFactory.open()` cũng không đồng nghĩa với Service Locator tổng quát: nó biểu diễn một dependency cụ thể và thời điểm cấp tài nguyên có ý nghĩa.

**Đánh đổi:** giảm chữ ký constructor bằng cách giấu phụ thuộc thường làm giảm khả năng điều hướng và khả năng phát hiện sai lắp ghép sớm.

## 9. Composition root nên tập trung nhưng không nhất thiết dài

Một root duy nhất rất dễ tìm, nhưng có thể phình lớn theo quy mô hệ thống. Có thể giữ tính điều hướng bằng cách **tập trung nơi điều phối** và **chia phần chi tiết theo module**:

```text
main()
  │
  ▼
ApplicationComposition
  ├── CatalogModule.create(settings)
  ├── PricingModule.choose(settings)
  ├── PersistenceModule.create(settings)
  └── CheckoutModule.create(catalog, pricing, receipts)
        │
        ▼
      CheckoutService
        │
        ▼
      CheckoutHandler
```

Một cách tổ chức tốt cho phép:

- Tìm **một ranh giới khởi động** trước tiên.
- Từ root, thấy **module nào sở hữu quyết định tạo/binding**.
- Các factory nhận rõ cấu hình và collaborator cần thiết, không tra cứu global tùy tiện.
- Nơi tạo tài nguyên có hợp đồng owner và đường cleanup rõ.
- Các entry point HTTP/CLI/worker có thể dùng lại module assembler khi phù hợp mà không nhân đôi mọi `new`.

Khi module assembler bắt đầu tạo nhiều dependency mà không được truyền đầu vào rõ, dùng config toàn cục ở mọi tầng hoặc mở listener ngay trong constructor, việc tách file đã không còn bảo đảm sự minh bạch. **Ranh giới quyền sở hữu và điểm bắt đầu nhận công việc** quan trọng hơn tên class có hậu tố `Module` hay `Factory`.

## 10. Tường minh về scope và ownership là một phần của chất lượng graph

Object graph không chỉ là mũi tên giữa các kiểu; mỗi instance có **vòng đời**.

```text
ApplicationRoot
  ├── SharedClientPool         [owner: application]
  ├── CheckoutService          [dùng chung nếu stateless/thread-safe]
  │
  ├── RequestScope #1
  │     ├── CheckoutRequest    [dữ liệu per-call]
  │     └── UnitOfWork #1      [owner: scope/request]
  │
  └── RequestScope #2
        ├── CheckoutRequest
        └── UnitOfWork #2
```

Wiring thủ công có lợi thế là ta nhìn thấy `new` và `try-with-resources` khi được viết rõ. Container có thể cung cấp scope định danh, callback hủy và validation, nhưng cấu hình scope có thể nằm xa consumer.

Một số đánh đổi đáng lưu ý:

| Quyết định | Lợi ích | Rủi ro cần quản lý |
|---|---|---|
| Chia sẻ client/pool cấp application | Giảm chi phí khởi tạo; dùng chung connection | Thread safety, shutdown ordering, owner |
| Đối tượng theo request | Cô lập state, có boundary đóng rõ | Propagation qua async, cleanup khi request lỗi |
| Transient/new mỗi lần resolve | Không tự chia sẻ instance giữa lần resolve | Tạo thừa object, chi phí và trách nhiệm dispose |
| Inject factory cho unit of work | Mở tài nguyên đúng lúc | Factory tạo xong ai đóng? Đóng khi exception? |
| Container tự quản lý disposable | Giảm cleanup thủ công | Semantics destroy khác nhau theo container/registration |

**Scope không đồng nghĩa thời gian sống thực tế**. Một transient được inject vào singleton và giữ trong field có thể tồn tại suốt đời singleton. Một request-scoped object bị đưa ra ngoài scope có thể bị sử dụng sau khi đã đóng. Tính tường minh giúp phát hiện các trường hợp này, nhưng vẫn cần kiểm thử vòng đời và contract của framework.

Khi shutdown, consumer đang dùng dependency cần dừng trước khi dependency bị đóng. Với graph đơn giản, thứ tự đóng thường ngược thứ tự lắp:

```text
Tạo: ClientPool → Repository → Worker
Đóng: Worker → Repository → ClientPool
```

Nếu có thread/callback bất đồng bộ, phải ngừng nhận công việc và chờ các thao tác đang chạy theo chính sách trước khi đóng pool. Chỉ nhìn constructor không thể suy ra mọi ràng buộc shutdown đó.

## 11. Phát hiện lỗi sớm và khả năng debug

Ba cách composition có thể cho những **thời điểm báo lỗi** khác nhau:

| Lỗi | Wiring Java trực tiếp | Container reflection | Container codegen/AOT |
|---|---|---|---|
| Thiếu đối số constructor tại lời gọi `new` | Compiler có thể báo ngay | Container tra metadata/registration; tùy eager/lazy validation | Generator/compiler có thể báo khi build nếu graph được biết |
| Không chọn được implementation cho interface | Cần code chọn cụ thể; có thể fail fast ở root | Có thể báo tại build/startup/resolve | Có thể báo build/startup nếu phân tích đủ registration |
| Cấu hình mode không hợp lệ | Parse tại runtime/startup | Vẫn cần parse/validate | Vẫn cần parse/validate |
| Singleton giữ resource của request | Không được compiler tự phát hiện tổng quát | Có thể có scope validation, không bảo đảm mọi trường hợp | Tùy generator và kiểm tra scope |
| Hạ tầng mạng không sẵn sàng | Phát hiện khi readiness hoặc dùng | Tương tự | Tương tự |
| Callback còn dùng pool khi shutdown | Cần lifecycle test/coordinator | Cần lifecycle test/coordinator | Cần lifecycle test/coordinator |

Không nên kết luận “container reflection chỉ phát hiện lỗi khi request đến” hoặc “code generation phát hiện tất cả lỗi trong build”. Container có thể khởi tạo/kiểm tra graph sớm, trong khi cấu hình hoặc nhánh động vẫn chỉ xuất hiện lúc chạy. Java compiler biết chữ ký và kiểu, nhưng **không chứng minh implementation đúng môi trường, an toàn đồng thời hoặc luôn sẵn sàng**.

Khi điều tra lỗi, **thông báo thể hiện dependency path** rất hữu ích:

```text
CheckoutHandler
  → CheckoutService
    → ReceiptSink
      → Missing binding for database-backed ReceiptSink
```

Một container có báo cáo graph rõ ràng đôi khi giúp debug nhanh hơn wiring thủ công phân tán. Một root nhỏ rõ ràng đôi khi lại nhanh hơn đọc hàng chục annotation. Hãy đánh giá cả **chất lượng công cụ và convention của dự án**, không chỉ so tên cơ chế.

## 12. So sánh ba phương án theo tình huống

Bảng sau là **xu hướng thường gặp**, không phải điểm hiệu năng tuyệt đối:

| Tiêu chí | Manual wiring tường minh | Factory/module assembler | DI container |
|---|---|---|---|
| Xem constructor của service | Rõ nếu dùng constructor injection | Rõ nếu giữ constructor injection | Vẫn rõ nếu giữ constructor injection |
| Tìm implementation cụ thể | Theo lệnh `new` ở root | Theo lời gọi vào module factory | Theo registration/config/diagnostics |
| Chi phí mã wiring ở graph nhỏ | Thường thấp | Có thể tăng do thêm tầng | Thường có setup framework |
| Chi phí wiring ở graph lớn | Có thể dài và lặp | Giảm lặp nếu module hợp lý | Có thể tự động hóa nhiều registration |
| Phát hiện thiếu tham số | Compile ở nơi gọi `new` | Compile ở nơi gọi constructor/factory | Tùy graph validation/build/startup |
| Scope và lifecycle | Tự tổ chức | Tự tổ chức theo module | Có thể được hỗ trợ; vẫn cần cấu hình |
| Phụ thuộc vào framework | Không | Không nhất thiết | Có |
| Refactor thêm collaborator | Sửa các điểm khởi tạo | Có thể chỉ sửa một assembler | Có thể không sửa wiring cơ học nếu binding sẵn |
| Debug sai binding | Đọc logic chọn ở root | Đọc factory và cấu hình | Đọc registry/qualifier/profile/graph report |

Đừng biến bảng thành bảng xếp hạng. Một library muốn chạy độc lập với framework có thể thích manual wiring; một ứng dụng Spring đã phụ thuộc sâu vào lifecycle của framework có thể thích dùng container sẵn có; một hệ thống nhiều module có thể kết hợp container ở ranh giới ứng dụng với factory hẹp cho tài nguyên theo transaction.

## 13. Quy trình quyết định có căn cứ

Trước khi thay cách lắp ghép, hãy trả lời:

### Bước 1 — Graph thực sự lớn và thay đổi ra sao?

Có bao nhiêu collaborator có vòng đời đáng kể? Bao nhiêu implementation có thể được chọn theo cấu hình? Bao nhiêu entry point cần graph tương tự? Có bao nhiêu dòng wiring **thực sự lặp** chứ không chỉ nhiều dòng?

Nếu graph chỉ có vài lớp, Java thuần có thể là lời giải hoàn chỉnh. Nếu việc thêm một dependency khiến phải sửa hàng chục root trùng lặp, vấn đề có thể là **tổ chức composition**, chưa chắc phải thêm container ngay.

### Bước 2 — Dependency có còn công khai ở constructor không?

Dù dùng tool nào, consumer nên khai báo những collaborator cần thiết một cách tường minh. Nếu một giải pháp rút ngắn constructor bằng cách inject `ApplicationContext` rồi lookup mọi thứ, hãy cân nhắc chi phí mất khả năng điều hướng và test đơn vị.

### Bước 3 — Nơi nào chọn implementation và scope?

Có thể chỉ rõ:

- Cấu hình nào chọn `StandardPricePolicy` hay `PromoPricePolicy`?
- Khi thay policy, thay root hay thay registration nào?
- Hai consumer có phải chia sẻ `ReceiptSink` không?
- Resource có được phép sống vượt request không?
- Ai đóng client khi startup thất bại hoặc application shutdown?

Nếu không trả lời được, đổi công nghệ wiring cũng chưa giải quyết được vấn đề thiết kế.

### Bước 4 — Chất lượng feedback lúc lỗi ra sao?

Đo xem thiếu binding được phát hiện khi nào, thông báo lỗi có dependency path không, kiểm tra scope có đáng tin không. Viết test composition cho các mode chính thay vì chỉ chạy một happy path.

### Bước 5 — Đo chi phí con người lẫn chi phí máy

Một bài toán phù hợp để đo thử: thêm `AuditTrail` vào `CheckoutService` và tìm tất cả nơi phải sửa. Đồng thời đo thời gian startup hoặc kích thước graph nếu chúng là yêu cầu của sản phẩm.

**Chỉ chọn kỹ thuật phức tạp hơn khi lợi ích nhìn thấy được** về code lặp, thay đổi, lifecycle, khả năng điều hướng hoặc vận hành — chứ không phải chỉ vì dự án đạt số lượng class nào đó.

## 14. Các lỗi thường gặp

| Hiện tượng | Vấn đề thật | Cách cải thiện |
|---|---|---|
| “Dùng container sẽ hết mọi lệnh `new`” | Nhầm DI với cấm tạo object dữ liệu | Giữ `new` cho DTO/value object; cấp collaborator có ý nghĩa từ ngoài |
| Một root dài hàng nghìn dòng, không chia module | Khó điều hướng dù wiring tường minh | Tách assembler theo chức năng nhưng giữ root điều phối |
| Nhiều factory tự đọc cấu hình global | Graph có dependency ẩn | Truyền settings và collaborator qua parameter rõ |
| Business service inject container tổng quát | Service Locator, khó test và khó biết binding | Constructor injection, selector/factory hẹp khi cần |
| Thêm interface, factory và qualifier cho mọi class | Boilerplate vượt nhu cầu | Chỉ tạo abstraction khi có ranh giới/biến động hợp lý |
| Cho rằng ít LOC wiring là ít chi phí tổng | Dời chi phí sang debug hoặc runtime validation | Đo cả feedback, ownership và thay đổi |
| Cho rằng manual wiring luôn chạy nhanh hơn | Bỏ qua khởi tạo tài nguyên và workload thực | Đo startup, resolution và I/O trên ứng dụng |
| Cho rằng container biết lifetime đúng | Có thể mắc captive dependency | Kiểm tra scope và owner cho từng tài nguyên |
| Chỉ test use case, bỏ qua composition | Sai lựa chọn implementation hoặc thiếu registration | Test graph theo cấu hình quan trọng |
| Chỉ nhìn DI annotation để suy ra lớp nào chạy | Có thể có qualifier, profile, override hoặc proxy | Truy tới registration và cấu hình thực tế |

Tính tường minh không nhằm “ghi mọi quyết định lên một file”, mà nhằm **giảm số sự thật phải đoán** khi sửa hoặc vận hành. Một sơ đồ phụ thuộc có tài liệu, test composition và thông báo lỗi rõ đôi khi có giá trị hơn việc tranh luận thuần túy về số dòng Java và số annotation.

## 15. Bài tập thực hành

**Bài tập 1 — Điều hướng graph từ hai đầu.** Mở `ExplicitWiringDemo`, bắt đầu ở `main()` và lần tới `CheckoutService.checkout(...)`. Sau đó bắt đầu từ constructor `CheckoutService` và tìm ngược tới `assemble(...)`. Ghi lại ít nhất ba quyết định composition không hiển thị trên chữ ký constructor.

**Bài tập 2 — Thêm một dependency.** Giả sử service cần `AuditTrail.record(orderId)` sau khi lưu biên bản. Phác thảo constructor mới, thay đổi tối thiểu ở `assemble(...)` và fake cần thêm trong `ExplicitWiringCheck`. Phân biệt lỗi bị compiler phát hiện với lỗi logic audit chỉ test mới thấy.

**Bài tập 3 — Chia module assembler.** Tách phần tạo `Catalog`, `PricePolicy` và `ReceiptSink` thành các factory có tên rõ, nhưng để `assemble(...)` tiếp tục điều phối. Kiểm tra `main` vẫn cho kết quả như cũ. Liệt kê những quyết định còn thấy ngay tại root và những quyết định cần điều hướng vào factory.

**Bài tập 4 — Phát hiện Service Locator.** Viết lại phản ví dụ `CheckoutService(ServiceRegistry)` thành constructor nhận ba contract rõ ràng. Dùng một fake `PricePolicy` để xác minh service không cần registry trong unit test.

**Bài tập 5 — So sánh chi phí thật.** Với một graph 6 class và một graph 60 class (mô phỏng bằng sơ đồ), lập bảng tiêu chí: mã lặp, thời điểm lỗi, tìm binding, scope, build/startup và đào tạo người mới. Đề xuất manual wiring, module assembler hoặc container cho mỗi tình huống **kèm điều kiện**, không xếp hạng tuyệt đối.

**Bài tập 6 — Lifecycle.** Đổi `ReceiptSink` thành một adapter sở hữu `AutoCloseable` client. Xác định ai tạo/đóng client, ai dừng request trước khi đóng, và test startup thất bại sau khi client đã mở. Không để `CheckoutService` đóng client được inject chỉ vì nó đang dùng client.

**Bài tập 7 — Cấu hình đa implementation.** Bổ sung một `BulkPricePolicy` dành cho đơn số lượng lớn. Quyết định nên chọn khi startup hay theo từng request, giải thích vì sao. Nếu chọn theo request, đánh giá liệu cần `PricePolicySelector` hay chỉ cần truyền strategy theo lời gọi.

### Câu hỏi tự kiểm tra

1. Constructor tường minh về dependency có cho biết implementation cụ thể được chọn không?
2. Vì sao một root Java thuần có thể dễ debug nhưng vẫn khó bảo trì khi graph lớn?
3. Khi nào module factory giúp điều hướng và khi nào nó làm dependency bị ẩn?
4. Vì sao `container.resolve(...)` tại composition root khác với lookup container bên trong use case?
5. Ít dòng wiring có bảo đảm ít chi phí bảo trì hơn không?
6. Sinh mã lắp graph có thể kiểm tra điều gì sớm, và điều gì vẫn là lỗi runtime?
7. Một transient có chắc được tạo lại ở mỗi lần gọi method của singleton không?
8. Làm thế nào kiểm tra container đang chọn đúng `PricePolicy` cho production?
9. Khi thêm collaborator, compiler giúp gì cho manual wiring?
10. Chỉ số hoặc bằng chứng nào nên có trước khi quyết định chuyển từ Java thuần sang DI container?

**Gợi ý:** (1) Không, phải xem composition; (2) mã khởi tạo và cấu hình có thể lặp/trải rộng; (3) tốt khi ranh giới và tham số rõ, xấu khi tra global hoặc tạo ngầm; (4) root lắp ghép rồi inject, use case lookup ẩn dependency; (5) không; (6) những quan hệ biết tại build, không phải network/config động; (7) không, chỉ khi resolve mới; (8) test composition + kiểm tra binding/profile; (9) báo lời gọi constructor thiếu/sai kiểu; (10) chi phí thay đổi, lỗi binding, lifecycle, hiệu năng và mức độ lặp thực tế.

## Ghi nhớ

- **Tường minh có hai tầng:** service công khai collaborator qua constructor; composition cho thấy cách chọn implementation, scope và ownership.
- **Điều hướng là khả năng lần được đường từ entry point tới implementation và ngược lại**, không chỉ là tìm tên interface trong IDE.
- **Chi phí lắp ghép nhiều chiều:** mã wiring, thay đổi, validation, startup, runtime, debugging, onboarding và lifecycle đều đáng cân nhắc.
- **Wiring Java thuần, module assembler và DI container đều có chỗ dùng.** Đừng chọn chỉ vì ít dòng `new` hay nhiều annotation.
- **Giữ constructor injection và kiểm thử bằng fake**, bất kể công nghệ lắp graph. Kiểm thử composition riêng để biết đúng implementation được chọn.
- **Scope, ownership và thứ tự đóng vẫn phải đúng.** Container giúp tự động hóa nhưng không thể thay thế quyết định thiết kế về vòng đời.
- **Chọn mức độ tự động hóa dựa trên vấn đề đo/quan sát được**, không dựa vào niềm tin rằng manual luôn tốt hơn container hoặc ngược lại.
