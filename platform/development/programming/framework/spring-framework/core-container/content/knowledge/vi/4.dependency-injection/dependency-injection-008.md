# Nhận diện quá nhiều phụ thuộc và trách nhiệm cần tách — Spring Framework Core Container

## 1. Mục tiêu: constructor dài là dấu hiệu cần phân tích

Constructor injection giúp dependency của một class trở nên **hiện rõ trong chữ ký**. Chính vì vậy, khi một service phải nhận 6–10 collaborators, bạn sẽ nhìn thấy ngay độ phức tạp mà field injection hoặc service locator trước đó có thể đã che đi.

**Nhiều tham số không tự động là lỗi.** Không có quy tắc của Java hay Spring rằng “constructor từ 5 tham số trở lên là sai”. Cần xem **các dependency đại diện những trách nhiệm nào**, những thay đổi nghiệp vụ nào khiến class bị sửa, mức độ liên kết của các method và độ khó kiểm thử.

Ví dụ `OrderService` cần xử lý báo giá, kiểm tra kho, thu tiền, sắp xếp giao hàng, gửi biên nhận và audit. Một constructor nhận 7 dependency có thể là triệu chứng class đã ôm nhiều lý do thay đổi. Refactor tốt là **tách các trách nhiệm có ranh giới rõ**, không phải chỉ giấu bảy tham số trong một object khác.

Sau bài này, bạn có thể:

1. Nhận diện dấu hiệu của **quá nhiều phụ thuộc**, **low cohesion**, **high coupling** và class có nhiều lý do thay đổi.
2. Phân biệt **số dependency** với **chất lượng thiết kế**; đánh giá cả thời điểm cùng thay đổi, nhóm method và nhiệm vụ thật của service.
3. Lập bản đồ một class đang sử dụng collaborator nào cho từng nghiệp vụ, tìm cụm trách nhiệm có thể tách.
4. Refactor `OrderService` thành `QuoteService`, `PurchaseService`, `FulfillmentService` và `OrderWorkflow` có cấu trúc dependency minh bạch.
5. Wiring các lớp sau tách bằng `@Configuration`/`@Bean` và **constructor injection** trong Spring Framework thuần.
6. Kiểm chứng bằng Java 17+, Maven, `javac`/`java` và stdout xác định.
7. Tránh anti-pattern: `ApplicationContext.getBean(...)` trong nghiệp vụ, “God facade”, generic dependency bag, truyền một container khổng lồ và trừu tượng hóa quá mức.
8. Thiết kế unit test và smoke test để bảo đảm refactor **giữ nguyên hành vi** ở các điều kiện quan trọng.

**Phạm vi:** Đây là kỹ thuật **đánh giá và tách trách nhiệm từ dấu hiệu quá nhiều constructor dependencies** trong chương *Tiêm phụ thuộc*. Không cần Spring Boot, database, message broker, kiến trúc microservices hay DI framework khác.

## 2. Ví dụ trước refactor: một class giải quyết quá nhiều việc

Hãy tưởng tượng một service thực hiện toàn bộ quy trình:

~~~java
// Phác thảo trước refactor: KHÔNG phải file Java đầy đủ.
final class OrderService {
    private final PriceCatalog catalog;
    private final DiscountPolicy discount;
    private final StockGateway stock;
    private final PaymentGateway payment;
    private final ShippingGateway shipping;
    private final ReceiptSender receipts;
    private final AuditSink audit;

    OrderService(
            PriceCatalog catalog,
            DiscountPolicy discount,
            StockGateway stock,
            PaymentGateway payment,
            ShippingGateway shipping,
            ReceiptSender receipts,
            AuditSink audit) {
        this.catalog = java.util.Objects.requireNonNull(catalog);
        this.discount = java.util.Objects.requireNonNull(discount);
        this.stock = java.util.Objects.requireNonNull(stock);
        this.payment = java.util.Objects.requireNonNull(payment);
        this.shipping = java.util.Objects.requireNonNull(shipping);
        this.receipts = java.util.Objects.requireNonNull(receipts);
        this.audit = java.util.Objects.requireNonNull(audit);
    }

    // quote(...), buy(...), ship(...), notify(...), audit(...) ...
}
~~~

Đoạn trên chỉ minh họa **dependency list**; dấu `...` ở comment không phải mã nghiệp vụ runnable. Một service như vậy có thể có nhiều method, mỗi method chỉ sử dụng một phần trong bảy collaborators.

| Nhóm nghiệp vụ | Collaborators tương ứng | Lý do dễ phải thay đổi |
| --- | --- | --- |
| Báo giá | `PriceCatalog`, `DiscountPolicy` | Quy tắc giá và khuyến mãi |
| Đặt mua/thu tiền | `StockGateway`, `PaymentGateway` | Tồn kho và tích hợp thanh toán |
| Hoàn tất đơn | `ShippingGateway`, `ReceiptSender`, `AuditSink` | Vận chuyển, thông báo, nhật ký kiểm toán |

Nếu class `OrderService` bị sửa khi thay cách tính khuyến mãi, khi đổi nhà cung cấp thanh toán **và** khi thêm kênh gửi biên nhận, đó là nhiều **lý do thay đổi** nằm trong một lớp. Người bảo trì phải hiểu rộng hơn phần họ đang sửa, trong khi tests cho báo giá có thể phải tạo cả bảy fake không liên quan.

**Tuy nhiên:** không phải cứ có bảy constructor parameters là chắc chắn vi phạm Single Responsibility Principle (SRP). Một adapter orchestration thật sự có nhiệm vụ điều phối bảy collaborator và không chứa các logic riêng đôi khi vẫn hợp lý, nhất là ở ranh giới application service. Hãy quan sát các method và thay đổi thực tế trước khi kết luận.

## 3. Những dấu hiệu quan trọng hơn một con số

### 3.1. Method clusters dùng những nhóm dependency khác nhau

Lập ma trận:

| Method trong lớp cũ | Catalog | Discount | Stock | Payment | Shipping | Receipt | Audit |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `quote()` | X | X | | | | | |
| `charge()` | | | X | X | | | |
| `fulfill()` | | | | | X | X | X |
| `placeOrder()` | X | X | X | X | X | X | X |

Ma trận thể hiện ba cụm khá độc lập và một method **điều phối** gọi các bước. Nếu `placeOrder()` còn tự implement các công thức giá, trạng thái thanh toán và formatting biên nhận, nó trở thành “god method”. Nếu method ấy chỉ gọi các bước đã tách rõ, nó có vai trò orchestration dễ hiểu.

### 3.2. Cohesion và coupling

- **Cohesion (độ gắn kết):** các method và dữ liệu của một class có cùng phục vụ một trách nhiệm rõ ràng không? Một `QuoteService` xử lý các phép tính báo giá thường cohesive hơn class vừa báo giá vừa gửi email.
- **Coupling (mức độ phụ thuộc):** lớp cần biết bao nhiêu API hoặc chi tiết dễ đổi? Class phụ thuộc vào quá nhiều client cụ thể có thể bị kéo theo thay đổi ở nhiều hệ thống.
- **Change coupling:** nhiều feature/bugfix khác nhau thường sửa cùng class vì những trách nhiệm không liên quan. Nếu mỗi lần đổi kênh thông báo đều có nguy cơ ảnh hưởng tính giá, ranh giới đang kém rõ.
- **Test friction:** unit test một quy tắc báo giá vẫn phải dựng payment/stock/shipping/email mocks mà không dùng tới; đây là tín hiệu liên kết không cần thiết.
- **Độ khó nêu trách nhiệm:** nếu câu giải thích class phải nối “và… và… và…”, cần thử viết lại hợp đồng ngắn gọn hơn.

### 3.3. Dấu hiệu cần kiểm chứng, không phải quy tắc tuyệt đối

Một constructor với hai dependencies vẫn có thể trộn hai trách nhiệm hoàn toàn khác nhau. Một class infrastructure như composite engine, adapter hoặc orchestrator đôi khi cần năm collaborators nhưng có **một nhiệm vụ nhất quán**. Kết luận dựa vào **lý do thay đổi và mối quan hệ trong nghiệp vụ**, không chỉ số dòng code, số fields hay số tham số.

Không tách class chỉ để vượt qua một rule linter kiểu `max-params=4`. Nếu việc tách khiến bạn phải nhảy qua tám lớp pass-through mà không cải thiện hiểu biết, có thể đó là **overengineering**.

## 4. Lập bản đồ trách nhiệm trước khi động vào code

Quy trình hữu ích:

1. **Đọc public API:** các operation nào thật sự thuộc class?
2. **Liệt kê dependency và vai trò:** mỗi dependency được dùng ở method nào, cho một kết quả gì?
3. **Nhóm những method thay đổi vì cùng lý do:** pricing/discount, purchase/stock/payment, fulfillment/shipping/receipt/audit.
4. **Xác định điểm giao:** lớp điều phối chỉ nên giữ việc kết nối các bước, không copy toàn bộ thuật toán của chúng.
5. **Tách một cụm trước:** dùng kỹ thuật Extract Class/Extract Service; đưa dữ liệu đầu vào/đầu ra qua kiểu có ý nghĩa như record.
6. **Viết unit test của cụm vừa tách**, rồi thêm Spring wiring test để kiểm tra bean candidate.
7. **Lặp lại theo bằng chứng** cho tới khi mỗi lớp có trách nhiệm rõ; dừng nếu tách thêm chỉ tạo forwarding methods.
8. **So hành vi trước–sau**, đặc biệt các lỗi payment/stock, ordering của side effects và boundary conditions.

### Mục tiêu thiết kế sau refactor

~~~mermaid
flowchart TD
    W["OrderWorkflow"] --> P["PurchaseService"]
    W --> F["FulfillmentService"]
    P --> Q["QuoteService"]
    P --> S["StockGateway"]
    P --> Pay["PaymentGateway"]
    Q --> Cat["PriceCatalog"]
    Q --> D["DiscountPolicy"]
    F --> Ship["ShippingGateway"]
    F --> R["ReceiptSender"]
    F --> A["AuditSink"]
~~~

**Đọc sơ đồ theo chiều consumer → dependency.** `OrderWorkflow` điều phối hai bước lớn. `QuoteService` chỉ tính giá; `PurchaseService` phối hợp báo giá/kho/thanh toán; `FulfillmentService` sắp xếp giao hàng và ghi nhận việc hoàn tất.

Các nhóm mới không nhất thiết ít tổng bean hơn class cũ. Mục tiêu là **giảm phạm vi hiểu và phạm vi thay đổi của mỗi thành phần**. Dependency graph vẫn biểu diễn đúng nghiệp vụ, thay vì “giấu” một graph phức tạp sau một interface mơ hồ.

## 5. Những thay đổi cụ thể trong thiết kế

| Trước | Sau | Lợi ích |
| --- | --- | --- |
| `OrderService` tự xử lý bảng giá và giảm giá | `QuoteService` phụ thuộc `PriceCatalog` và `DiscountPolicy` | Test báo giá độc lập khỏi gateway bên ngoài |
| `OrderService` tự giữ logic stock/payment | `PurchaseService` phụ thuộc `QuoteService`, `StockGateway`, `PaymentGateway` | Tập trung hợp đồng đặt mua và thu tiền |
| `OrderService` tự gọi shipping/receipt/audit | `FulfillmentService` phụ thuộc ba collaborator có liên quan đến hoàn tất | Thay đổi kênh gửi/hậu cần không ảnh hưởng công thức tính giá |
| Method chính biết đủ bảy collaborators | `OrderWorkflow` nhận `PurchaseService` và `FulfillmentService` | Orchestration dễ đọc, ít chi tiết |
| Dữ liệu chuyền bằng nhiều tham số rời rạc | `OrderRequest`, `Quote` và `Purchase` là các records mang thông tin có ý nghĩa | Hợp đồng rõ, giảm nhầm thứ tự tham số |

**Cẩn thận với phương thức thanh toán và side effects:** tách class không tự sinh transaction phân tán. Ví dụ demo đặt chỗ trong kho trước khi thu tiền, rồi mới xếp giao hàng. Nếu thu tiền lỗi sau khi giữ kho, hệ thống thực cần compensation/idempotency/transaction policy. Việc refactor **không được lén thay thứ tự side effects** nếu hợp đồng trước đây phụ thuộc vào thứ tự.

## 6. Ví dụ Spring Framework + Java 17+ có thể chạy

Project minh họa dùng **Spring Framework 6.2.19** (cố định cho ví dụ, không hàm ý mới nhất), JDK 17+ và Maven. Không cần Spring Boot, database, HTTP server hay một payment provider thật. Các gateway được thay bằng implementation **deterministic trong bộ nhớ** để quan sát ranh giới trách nhiệm.

~~~text
order-responsibilities-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── OrderResponsibilitiesDemo.java
~~~

### 6.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>order-responsibilities-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.OrderResponsibilitiesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven tải thêm dependencies transitively từ `spring-context`. Muốn dùng `javac` trực tiếp phải cung cấp các Spring JAR liên quan cho compiler/launcher.

### 6.2. File src/main/java/demo/OrderResponsibilitiesDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class OrderResponsibilitiesDemo {
    private OrderResponsibilitiesDemo() {}

    public record OrderRequest(String sku, int quantity) {
        public OrderRequest {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    public record Quote(OrderRequest request, int totalCents) {}
    public record Purchase(OrderRequest request, int totalCents,
                           String paymentId) {}

    public interface PriceCatalog {
        int unitPrice(String sku);
    }

    public interface DiscountPolicy {
        int discountCents(int subtotal);
    }

    public interface StockGateway {
        void reserve(String sku, int quantity);
    }

    public interface PaymentGateway {
        String charge(int totalCents);
    }

    public interface ShippingGateway {
        String schedule(String sku, int quantity);
    }

    public interface ReceiptSender {
        void send(String receipt);
    }

    public interface AuditSink {
        void record(String event);
    }

    public static final class RecordingReceiptSender
            implements ReceiptSender {
        private final List<String> sent = new ArrayList<>();

        @Override
        public void send(String receipt) {
            sent.add(receipt);
        }

        public List<String> snapshot() {
            return List.copyOf(sent);
        }
    }

    public static final class RecordingAuditSink implements AuditSink {
        private final List<String> events = new ArrayList<>();

        @Override
        public void record(String event) {
            events.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static final class QuoteService {
        private final PriceCatalog catalog;
        private final DiscountPolicy discount;

        public QuoteService(PriceCatalog catalog, DiscountPolicy discount) {
            this.catalog = Objects.requireNonNull(catalog);
            this.discount = Objects.requireNonNull(discount);
        }

        public Quote quote(OrderRequest request) {
            Objects.requireNonNull(request);
            int unitPrice = catalog.unitPrice(request.sku());
            if (unitPrice <= 0) {
                throw new IllegalArgumentException("invalid unit price");
            }
            int subtotal = Math.multiplyExact(unitPrice, request.quantity());
            int reduction = discount.discountCents(subtotal);
            if (reduction < 0 || reduction > subtotal) {
                throw new IllegalArgumentException("invalid discount");
            }
            return new Quote(request, Math.subtractExact(subtotal, reduction));
        }
    }

    public static final class PurchaseService {
        private final QuoteService quotes;
        private final StockGateway stock;
        private final PaymentGateway payments;

        public PurchaseService(
                QuoteService quotes, StockGateway stock,
                PaymentGateway payments) {
            this.quotes = Objects.requireNonNull(quotes);
            this.stock = Objects.requireNonNull(stock);
            this.payments = Objects.requireNonNull(payments);
        }

        public Purchase buy(OrderRequest request) {
            Quote quote = quotes.quote(request);
            stock.reserve(request.sku(), request.quantity());
            String paymentId = payments.charge(quote.totalCents());
            return new Purchase(request, quote.totalCents(), paymentId);
        }
    }

    public static final class FulfillmentService {
        private final ShippingGateway shipping;
        private final ReceiptSender receipts;
        private final AuditSink audit;

        public FulfillmentService(
                ShippingGateway shipping, ReceiptSender receipts,
                AuditSink audit) {
            this.shipping = Objects.requireNonNull(shipping);
            this.receipts = Objects.requireNonNull(receipts);
            this.audit = Objects.requireNonNull(audit);
        }

        public String fulfill(Purchase purchase) {
            String shipmentId = shipping.schedule(
                    purchase.request().sku(), purchase.request().quantity());
            String result = "payment=" + purchase.paymentId()
                    + ",shipment=" + shipmentId
                    + ",total=" + purchase.totalCents();
            receipts.send(result);
            audit.record("fulfilled:" + purchase.request().sku());
            return result;
        }
    }

    public static final class OrderWorkflow {
        private final PurchaseService purchases;
        private final FulfillmentService fulfillment;

        public OrderWorkflow(
                PurchaseService purchases,
                FulfillmentService fulfillment) {
            this.purchases = Objects.requireNonNull(purchases);
            this.fulfillment = Objects.requireNonNull(fulfillment);
        }

        public String run(OrderRequest request) {
            Purchase purchase = purchases.buy(request);
            return fulfillment.fulfill(purchase);
        }

        public PurchaseService purchases() {
            return purchases;
        }

        public FulfillmentService fulfillment() {
            return fulfillment;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PriceCatalog priceCatalog() {
            return sku -> {
                if (!"BOOK".equals(sku)) {
                    throw new IllegalArgumentException("unknown sku");
                }
                return 150;
            };
        }

        @Bean
        public DiscountPolicy discountPolicy() {
            return subtotal -> subtotal >= 300 ? 20 : 0;
        }

        @Bean
        public StockGateway stockGateway() {
            return (sku, quantity) -> {
                if (quantity > 5) {
                    throw new IllegalArgumentException("not enough stock");
                }
            };
        }

        @Bean
        public PaymentGateway paymentGateway() {
            return amount -> "PAY-" + amount;
        }

        @Bean
        public ShippingGateway shippingGateway() {
            return (sku, quantity) -> "SHIP-" + sku + "-" + quantity;
        }

        @Bean
        public RecordingReceiptSender receiptSender() {
            return new RecordingReceiptSender();
        }

        @Bean
        public RecordingAuditSink auditSink() {
            return new RecordingAuditSink();
        }

        @Bean
        public QuoteService quoteService(
                PriceCatalog catalog, DiscountPolicy discount) {
            return new QuoteService(catalog, discount);
        }

        @Bean
        public PurchaseService purchaseService(
                QuoteService quotes, StockGateway stock,
                PaymentGateway payments) {
            return new PurchaseService(quotes, stock, payments);
        }

        @Bean
        public FulfillmentService fulfillmentService(
                ShippingGateway shipping, ReceiptSender receipts,
                AuditSink audit) {
            return new FulfillmentService(shipping, receipts, audit);
        }

        @Bean
        public OrderWorkflow orderWorkflow(
                PurchaseService purchases, FulfillmentService fulfillment) {
            return new OrderWorkflow(purchases, fulfillment);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderWorkflow workflow = context.getBean(OrderWorkflow.class);
            QuoteService quotes = context.getBean(QuoteService.class);
            RecordingReceiptSender sent =
                    context.getBean(RecordingReceiptSender.class);
            RecordingAuditSink audit =
                    context.getBean(RecordingAuditSink.class);

            OrderRequest request = new OrderRequest("BOOK", 2);
            System.out.println("workflowWired=" +
                    (workflow.purchases() == context.getBean(PurchaseService.class)
                     && workflow.fulfillment()
                     == context.getBean(FulfillmentService.class)));
            System.out.println("quoteTotal=" +
                    quotes.quote(request).totalCents());
            System.out.println("result=" + workflow.run(request));
            System.out.println("sent=" + sent.snapshot());
            System.out.println("audit=" + audit.snapshot());
            System.out.println("workflowSingleton=" +
                    (workflow == context.getBean(OrderWorkflow.class)));
        }
    }
}
~~~

**Đảm bảo bản demo có thể hiểu độc lập:**

- Một top-level public class `OrderResponsibilitiesDemo` khớp file; interfaces, records, services và config nằm trong cùng class dưới dạng nested types.
- Hai records `OrderRequest` và `Quote`/`Purchase` dùng Java 17. `OrderRequest` kiểm tra SKU và quantity tại constructor, `QuoteService` dùng `Math.multiplyExact`/`Math.subtractExact` để không âm thầm overflow.
- `QuoteService` nhận **hai collaborators** (giá và chiết khấu), không cần biết stock/payment/shipping.
- `PurchaseService` nhận **ba collaborators** (quote, stock, payment), chỉ thực hiện giai đoạn đặt mua.
- `FulfillmentService` nhận **ba collaborators** (shipping, receipts, audit), không tính tiền.
- `OrderWorkflow` nhận **hai service đã có nghĩa** và nối hai bước. Không chứa bảy gateway chi tiết, không phụ thuộc Spring API trong code nghiệp vụ.
- `@Bean` factory methods trong `AppConfig` dùng **method parameters để Spring resolve**. Không gọi trực tiếp các method `@Bean` khác ở chế độ `proxyBeanMethods=false`.
- Các gateway fake và hai recording adapters được quản lý bởi container; fake payment tạo mã `PAY-280`, fake shipping tạo `SHIP-BOOK-2`.
- Bộ đếm/recording adapters dùng `ArrayList` vì demo gọi đơn luồng. Nếu bean singleton có nhiều requests đồng thời, cần thiết kế concurrency và lifecycle thích hợp; `final` references không tự làm list thread-safe.
- Chương trình có đúng một lần thực hiện workflow; câu lệnh `quotes.quote(...)` trước đó chỉ tính dữ liệu và **không** reserve/charge/ship. Không có random, clock hoặc mã hash trong stdout.

### 6.3. Chạy bằng Maven và stdout cố định

Mở terminal ở thư mục `order-responsibilities-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Sáu dòng stdout chính xác do mã `main` in khi chạy thành công:**

~~~text
workflowWired=true
quoteTotal=280
result=payment=PAY-280,shipment=SHIP-BOOK-2,total=280
sent=[payment=PAY-280,shipment=SHIP-BOOK-2,total=280]
audit=[fulfilled:BOOK]
workflowSingleton=true
~~~

Giải thích `quoteTotal=280`: giá `150` × số lượng `2` = `300`; `DiscountPolicy` giảm `20` khi subtotal đạt ít nhất `300`, còn `280`. `PurchaseService` chuyển `280` cho payment fake, sau đó `FulfillmentService` ghi biên nhận và audit.

Các lệnh version và log Maven/Spring (nếu có) không thuộc **sáu dòng do chương trình in**. Các gateway ở đây là fake, nên mã `PAY-280` không chứng minh có giao dịch ngân hàng thật.

### 6.4. Chạy bằng javac/java trực tiếp

Spring API phải nằm trên compile/runtime classpath. Tạo file chứa đầy đủ dependencies:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/OrderResponsibilitiesDemo.java
java -cp "out:$(cat classpath.txt)" demo.OrderResponsibilitiesDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/OrderResponsibilitiesDemo.java
java -cp "out;$deps" demo.OrderResponsibilitiesDemo
~~~

Classpath separator trên Unix là `:` và trên Windows là `;`. Hai cách chạy thực hiện cùng phương thức `main`, cho cùng sáu dòng output. Nếu `javac` báo không tìm thấy `org.springframework...`, vấn đề đầu tiên là classpath/dependency chứ chưa phải lỗi constructor injection.

## 7. Tại sao bản tách trách nhiệm tốt hơn?

### 7.1. Giảm các lý do thay đổi cho từng lớp

Giả sử thêm một loại chiết khấu: thường sửa `DiscountPolicy` hoặc logic quote; không cần chỉnh sửa code shipping hoặc sender. Đổi email template: thay implementation `ReceiptSender` mà không cần đụng `QuoteService`. Nếu thay phương thức thanh toán, thay implementation `PaymentGateway` và kiểm thử `PurchaseService`.

Quan hệ này hữu ích hơn việc đo constructor length:

| Nhu cầu thay đổi | Trọng tâm bị ảnh hưởng |
| --- | --- |
| Đổi bảng giá/chiết khấu | `QuoteService` và collaborator của nó |
| Thay quy tắc giữ hàng/thu tiền | `PurchaseService` và gateways |
| Thay vận chuyển/thông báo | `FulfillmentService` và adapters |
| Thay thứ tự bước lớn trong use case | `OrderWorkflow` |

Điều này không có nghĩa **không bao giờ** sửa nhiều lớp cùng lúc. Một feature xuyên suốt có thể cần cập nhật cả workflow và hợp đồng dữ liệu, nhưng ranh giới rõ sẽ làm thay đổi dễ đánh giá hơn.

### 7.2. Giảm chi phí test

Trước refactor, test một phép tính giá có thể phải tạo/mock bảy dependencies để khởi tạo `OrderService`. Sau refactor, unit test `QuoteService` chỉ cần `PriceCatalog` và `DiscountPolicy`.

~~~java
// Snippet minh họa trong phạm vi truy cập các nested types của demo:
PriceCatalog prices = sku -> 100;
DiscountPolicy discount = subtotal -> 10;
QuoteService quotes = new QuoteService(prices, discount);

Quote q = quotes.quote(new OrderRequest("BOOK", 2));
System.out.println(q.totalCents()); // 190
~~~

Đây **không phải file Java độc lập**, cần đặt vào method/test phù hợp. Kết quả `190` = `100 × 2 − 10`. Test đó không phải tạo stock, payment, shipping, receipts hoặc audit. Vì vậy test nhanh và sát trách nhiệm được kiểm tra.

### 7.3. Wiring tổng thể vẫn cần được kiểm tra

Có thêm lớp không tự làm cấu hình Spring đúng. Trong ví dụ, `OrderWorkflow` phụ thuộc một `PurchaseService` và một `FulfillmentService`; Spring phải có bean phù hợp cho cả hai. Nếu thiếu `PaymentGateway`, startup thường thất bại khi tạo singleton `PurchaseService`/`OrderWorkflow`. Nếu có hai `PaymentGateway` candidates không thể chọn duy nhất, Spring cũng có thể báo lỗi ambiguity.

Kết hợp hai loại test:

- **Unit tests** cho Quote/Purchase/Fulfillment riêng; các fake phù hợp với mỗi trách nhiệm.
- **Spring wiring/smoke test** tạo context và kiểm tra `OrderWorkflow` nhận đúng beans, sau đó kiểm tra một luồng hợp lệ.

Không dùng Java `assert` không bật `-ea` để thay những điều kiện kiểm tra bắt buộc; dùng test assertions được thực thi hoặc `if (...) throw ...`.

## 8. Những cách “giảm tham số” nhưng không giải quyết vấn đề

### 8.1. Bọc tất cả dependency vào một túi

~~~java
// Anti-pattern minh họa:
record AllDependencies(
        PriceCatalog catalog, DiscountPolicy discount,
        StockGateway stock, PaymentGateway payment,
        ShippingGateway shipping, ReceiptSender receipts,
        AuditSink audit) {}

final class OrderService {
    OrderService(AllDependencies everything) {
        // Vẫn nắm và làm việc với đủ 7 collaborators.
    }
}
~~~

Số tham số bề mặt của constructor giảm từ 7 xuống 1 nhưng class vẫn có quyền truy cập đủ các trách nhiệm cũ. Nó không tăng cohesion, có thể chỉ **giấu coupling**. Một parameter object hợp lý phải **nhóm dữ liệu/hành vi cùng ý nghĩa domain**, không chỉ gom mọi service cho tiện.

### 8.2. Tiêm ApplicationContext rồi tự getBean

~~~java
// Anti-pattern minh họa:
final class OrderService {
    private final ApplicationContext context;

    OrderService(ApplicationContext context) {
        this.context = context;
    }

    void process() {
        PaymentGateway gateway = context.getBean(PaymentGateway.class);
        // Phụ thuộc thật bị giấu trong method.
    }
}
~~~

Đây là snippet chưa có imports và full implementation, **không phải code runnable**. Nó biến class thành **service locator consumer**: chữ ký constructor có một tham số, nhưng dependencies thật bị giấu đi, dễ lỗi muộn và khó unit test. Đôi lúc dùng context/provider là phù hợp ở infrastructure/composition root, nhưng không phải cách thông thường để làm gọn một business service.

### 8.3. Chuyển constructor arguments sang @Autowired fields

~~~java
// Anti-pattern minh họa cho collaborator bắt buộc:
@Autowired private PriceCatalog catalog;
@Autowired private PaymentGateway payment;
@Autowired private ShippingGateway shipping;
~~~

Các field declarations trên phải nằm trong một class hợp lệ và có imports; không phải file độc lập. Chuyển từ constructor sang field injection chỉ **che giấu** phụ thuộc khỏi API khởi tạo. Nếu class đang ôm nhiều trách nhiệm, việc chuyển sang field injection không tách được trách nhiệm nào.

### 8.4. Thêm facade chỉ chuyển tiếp mọi thứ

Một lớp `OrderFacade` có bảy public methods và chỉ gọi một lớp `OrderHelper` chứa toàn bộ thuật toán không cải thiện thực chất. Cần tách **quyền quyết định của từng phần** (tính giá, thanh toán, fulfillment) về đúng nơi. Một orchestration layer có giá trị khi nó thể hiện **luồng use case** và chủ yếu gọi các bước đã có trách nhiệm rõ.

### 8.5. Tách microservices quá sớm

SRP và constructor DI là **thiết kế lớp/module**, không bắt buộc tách một hệ thống thành bảy dịch vụ mạng độc lập. Việc chuyển payment/stock/shipping sang microservices có thêm lỗi mạng, eventual consistency và vận hành, không tự chữa low cohesion trong code ứng dụng.

## 9. Khi nào nên giữ một constructor tương đối dài?

Đừng tối ưu hình thức. Có thể giữ nhiều tham số khi:

- Các collaborator thực sự cùng phục vụ **một mục tiêu cohesive**, ví dụ một adapter tổng hợp dữ liệu từ nhiều backend.
- Class chỉ làm **orchestration rõ ràng**, không đồng thời sở hữu các chi tiết thay đổi độc lập; mỗi collaborator là một bước được thiết kế có chủ đích.
- Tách tiếp sẽ tạo quá nhiều pass-through wrappers mà không có hợp đồng mới hay khả năng test tốt hơn.
- Dependencies là những thành phần bắt buộc của một thuật toán, và một lớp khác chứa chúng không làm ranh giới rõ thêm.
- Nhóm dữ liệu được biểu diễn bằng value object domain hợp lệ và có invariant chung, chứ không đơn thuần là bag of services.

Câu hỏi quyết định không phải “bao nhiêu tham số” mà là: **Có thể mô tả trách nhiệm class trong một câu có nghĩa? Các method và dependencies có đi cùng nhau khi nghiệp vụ đổi không?**

Nếu constructor dài nhưng class cohesive, cải thiện trước bằng **đặt tên rõ ràng, phân nhóm ở mức module, composition root và tests**, thay vì chia tùy tiện.

## 10. Lỗi Spring DI liên quan đến refactor

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `UnsatisfiedDependencyException` | Một service mới cần collaborator chưa đăng ký | Kiểm tra `@Bean`/scan và constructor parameters |
| `NoSuchBeanDefinitionException` | Thiếu bean cho một interface ở graph mới | Khai báo adapter hoặc cấu hình test fake rõ ràng |
| `NoUniqueBeanDefinitionException` | Hai beans cùng type không có selection rule | Dùng `@Qualifier`/`@Primary` theo vai trò, không đoán |
| `BeanCurrentlyInCreationException` | Tách lớp nhưng sinh vòng constructor dependency | Vẽ lại graph, đưa trách nhiệm chung ra lớp khác; tránh cycle |
| Context refresh thành công, output sai | Logic bị di chuyển sai hoặc thứ tự side effects thay đổi | Regression tests cho các đường nghiệp vụ và audit |
| Constructor ít tham số nhưng class vẫn phức tạp | Đã chuyển sang `ApplicationContext`, dependency bag hoặc field injection | Xem lại trách nhiệm và hidden dependencies |
| Hàng loạt tiny services chỉ chuyển tiếp | Tách chỉ để giảm param count | Gộp lại nơi hợp đồng thực sự cohesive |
| Test quote phải mock payment/shipping | Quote logic chưa được tách khỏi workflow | Tách nghiệp vụ báo giá có inputs/outputs rõ |
| Singleton ghi state dùng chung không an toàn | Fake/list hoặc service mutable được gọi đa luồng | Thiết kế thread-safe/stateless, giới hạn scope |
| Purchase đã giữ hàng nhưng thu tiền lỗi | Thiếu chiến lược rollback/compensation | Thiết kế nghiệp vụ thật, không nhầm với DI refactor |
| Constructor mặc định tạo object thiếu dependency | Né wiring errors bằng trạng thái không hợp lệ | Constructor bắt buộc và validation/fail fast |
| `javac` không thấy package Spring | Thiếu Maven/JAR classpath | Sửa build/classpath trước khi chẩn đoán bean graph |

**Quan trọng:** Tách class có thể **làm lộ** vòng phụ thuộc từng bị che bởi service locator hoặc mutable fields. Đây là cơ hội sửa thiết kế dependency graph, không phải lý do quay lại cách ẩn dependencies.

## 11. Kế hoạch refactor có kiểm chứng

Một cách an toàn khi làm trên hệ thống đang chạy:

1. **Chụp lại hành vi hiện tại:** tests cho giá, discount, stock failure, payment failure, fulfillment và audit.
2. **Xác định invariant:** không thu tiền cho số lượng không hợp lệ; không gửi receipt trước khi có thanh toán hợp lệ; ghi audit ở đúng giai đoạn.
3. **Tách báo giá đầu tiên:** `QuoteService` trả `Quote` immutable, không biết payment/shipping. Bảo đảm quote cũ/mới giống nhau.
4. **Tách bước mua:** `PurchaseService` nhận `QuoteService` cùng các gateways của purchase; tạo `Purchase` hợp lệ.
5. **Tách bước hậu mua:** `FulfillmentService` nhận dữ liệu Purchase thay vì tự gọi lại pricing.
6. **Giữ orchestration mỏng:** `OrderWorkflow` chỉ thể hiện order của các bước và xử lý use-case level.
7. **Cập nhật Spring configuration:** đăng ký các beans và dependencies bằng factory method parameters/constructors, không gọi trực tiếp `@Bean` methods nếu `proxyBeanMethods=false`.
8. **Chạy unit tests, integration tests và failure-path tests**; đánh giá side effects/exception behavior có giữ đúng không.
9. **Đo mức độ dễ thay đổi/test**, không chỉ đếm tham số. Nếu xuất hiện pass-through layer không có lý do, cân nhắc gộp.
10. **Tài liệu hóa ranh giới và ownership** của side effects, nhất là transaction, retry, idempotency và audit.

### Những regression cases đáng có

| Trường hợp | Kỳ vọng chính |
| --- | --- |
| BOOK × 2, subtotal 300 | Discount 20; total 280 |
| BOOK × 1, subtotal 150 | Không discount; total 150 |
| SKU không hỗ trợ | Quote fail; không gọi payment/fulfillment |
| Quantity bằng 0 hoặc âm | `OrderRequest` từ chối trước side effects |
| Quantity vượt tồn kho giả lập (trên 5) | Stock báo lỗi; không charge |
| Payment fake ném lỗi | Không gửi receipt/không fulfill; cần đánh giá reserve compensation trong hệ thống thật |
| Shipping lỗi sau payment | Không thể chỉ retry mù quáng; cần policy/idempotency/compensation |
| Unit test QuoteService | Không cần khởi tạo Payment/Stock/Shipping |
| Wiring của OrderWorkflow | Inject đúng hai services, context startup thành công |

Chú ý: bảng này là **kế hoạch kiểm thử**, không phải lời khẳng định ví dụ console đã chạy tất cả cases. Chỉ happy path có sáu dòng stdout ở mục 6.3.

## 12. Bài tập có đáp án

**Bài 1.** Constructor có bảy tham số. Có chắc class sai SRP không?

**Đáp án:** Không. Đây là tín hiệu cần xét method clusters, change reasons, cohesion, coupling và test friction. Một orchestrator rõ ràng có thể có nhiều collaborator mà vẫn có một trách nhiệm nhất quán.

**Bài 2.** Vì sao truyền một `AllDependencies` vào constructor chưa phải refactor đủ tốt?

**Đáp án:** Nó giảm số tham số hiển thị nhưng giữ nguyên khả năng truy cập bảy collaborators và nhiều trách nhiệm. Không làm cho các thay đổi price/payment/shipping ít va chạm hơn.

**Bài 3.** Nếu QuoteService cần mock PaymentGateway trong unit test, điều gì có thể chưa đúng?

**Đáp án:** Logic báo giá còn phụ thuộc không cần thiết vào payment hoặc test đang dùng quá nhiều infrastructure. Tách tính giá khỏi bước thu tiền để quote unit test chỉ cần price catalog/discount.

**Bài 4.** Khi nào nên giữ `OrderWorkflow` thay vì gọi tất cả từ `main`?

**Đáp án:** Khi có một use case thực sự cần bảo đảm thứ tự Purchase→Fulfillment và cho nhiều entry points (CLI, web, jobs) dùng chung contract điều phối. Nếu ứng dụng rất nhỏ và không có orchestration rule, lớp này có thể chưa cần thiết.

**Bài 5.** Tách class có tự giải quyết transaction/payment failure không?

**Đáp án:** Không. Cần thiết kế side-effect ordering, idempotency, compensation và exception handling riêng. Refactor phải giữ hoặc cải thiện đúng hợp đồng nghiệp vụ, không chỉ cấu trúc class.

**Bài 6.** Có nên thay bảy constructor parameters bằng `ApplicationContext` để hết cảnh báo linter?

**Đáp án:** Không nên ở business service. Service locator giấu phụ thuộc thật, lỗi xuất hiện muộn và unit test phức tạp. Ưu tiên constructor injection với trách nhiệm rõ.

**Bài 7.** Vì sao `QuoteService` chỉ có hai collaborator có ích cho kiểm thử?

**Đáp án:** Nó chỉ yêu cầu catalogue và discount policy, nên fake đơn giản là đủ; test pricing không phụ thuộc shipping/notification/payment và dễ xác định khi thất bại.

**Bài 8.** Nếu thêm một wrapper chuyển tiếp vô nghĩa chỉ để constructor mỗi lớp còn tối đa 3 tham số, thiết kế có chắc tốt hơn không?

**Đáp án:** Không. Đó có thể là indirection không giá trị. Tiêu chí là cohesion, ranh giới trách nhiệm, khả năng thay đổi/test và tính dễ hiểu của dependency graph.

## 13. Checklist rà soát

- [ ] Có thể nêu trách nhiệm của mỗi service bằng một câu ngắn gọn.
- [ ] Constructor thể hiện dependency thật, không giấu trong service locator hoặc injected fields.
- [ ] Không dùng một ngưỡng tham số tùy ý làm kết luận duy nhất.
- [ ] Có ma trận method–dependency và biết những cụm trách nhiệm nào thay đổi cùng nhau.
- [ ] `QuoteService` không biết payment/shipping; `FulfillmentService` không tính giá.
- [ ] `OrderWorkflow` chỉ điều phối những bước có ý nghĩa, không ôm bảy clients.
- [ ] Value objects/records có contract và invariant rõ; không chỉ là “bag” chứa services.
- [ ] Cấu hình Spring inject collaborators bằng constructors hoặc `@Bean` method parameters.
- [ ] Chạy Java 17+ bằng Maven/`javac`/`java` và so **sáu dòng stdout** chính xác.
- [ ] Kiểm tra missing/ambiguous beans, cycles và business failure paths.
- [ ] Unit test các service nhỏ không cần Spring; smoke test context cho wiring.
- [ ] Không thêm tầng pass-through không cải thiện khả năng thay đổi/test.
- [ ] Side effects có ownership rõ: giữ kho, thu tiền, shipping, receipt, audit.
- [ ] Không kết luận refactor hoàn thành chỉ từ việc ít constructor parameters hơn.
- [ ] Tránh thay đổi thứ tự/số lần thực hiện nghiệp vụ một cách tình cờ.

**Kết luận:** Constructor injection không gây ra “quá nhiều dependencies” mà **làm chúng trở nên dễ nhìn**. Nếu một class có nhiều lý do thay đổi, method clusters ít liên quan và unit tests phải dựng các collaborator không dùng đến, hãy tách theo **trách nhiệm nghiệp vụ cohesive**. Đừng chỉ giấu dependencies trong một bag, context hoặc wrapper; hãy cải thiện **dependency graph, tính rõ ràng của hợp đồng và khả năng kiểm thử**.

### Tài liệu chính thức và khái niệm liên quan

- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
