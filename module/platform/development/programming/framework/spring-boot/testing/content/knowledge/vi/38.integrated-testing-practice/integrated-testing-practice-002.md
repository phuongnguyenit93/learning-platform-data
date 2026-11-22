# Viết unit test cho quy tắc nghiệp vụ có nhánh lỗi và điều kiện biên

## 1. Vì sao một happy-path test chưa đủ?

Trong **Spring Boot - testing**, nhóm **Thực hành tích hợp**, một chức năng nghiệp vụ có thể trả đúng trong ví dụ thông thường nhưng sai tại các ngưỡng quan trọng: số lượng bằng 0, vượt giới hạn, giá bằng 0, số tiền có ba chữ số thập phân, mức giảm giá vừa đủ điều kiện, tổng sau giảm giá vừa chạm ngưỡng miễn phí giao hàng hoặc tồn kho vừa thiếu một đơn vị.

**Unit test chất lượng phải chứng minh cả quy tắc đúng và các nhánh từ chối.** Điều này đòi hỏi test hợp đồng rõ ràng: một đầu vào hợp lệ dẫn đến kết quả số học và tương tác đúng, đầu vào lỗi dẫn đến exception đúng loại và không gây side effect. Không chỉ kiểm rằng có exception bất kỳ; phải hiểu thứ tự validation và tại sao một external port **không được gọi** khi dữ liệu đã không hợp lệ.

Bài thực hành chọn quy tắc **báo giá đơn hàng** để có đủ tình huống:
- Mã sản phẩm SKU phải hợp lệ và được chuẩn hóa.
- Số lượng nguyên từ **1 đến 20**, gồm cả hai biên.
- Đơn giá từ **0,01 đến 10.000,00** theo tiền tệ có hai chữ số thập phân.
- Coupon **SAVE10** giảm **10%** nếu **tổng trước giảm** ít nhất **100,00**.
- Tính giảm giá bằng **BigDecimal**, làm tròn **HALF_UP** đến hai chữ số.
- Kiểm tra số lượng hàng còn thông qua **InventoryPort**, là outbound dependency duy nhất.
- Nếu kho báo còn âm, xem đó là lỗi dữ liệu/hạ tầng; nếu còn ít hơn số lượng đặt, trả exception thiếu tồn kho.
- Phí giao hàng **12,00** nếu **tổng sau giảm** dưới **200,00**; bằng hoặc trên **200,00** thì miễn phí.
- Tổng cần thanh toán = tổng trước giảm − giảm giá + phí giao hàng.

Bộ ví dụ dùng **Java 17+, Spring Boot 3.4.5, Gradle, JUnit Jupiter, Mockito và MockitoExtension**. Đối tượng được kiểm thử là class Java thường, **không khởi Spring ApplicationContext**. Điều này có chủ đích: thuật toán báo giá không cần server, DataSource hoặc Spring proxy để có thể kiểm các nhánh nghiệp vụ. Khi cần kiểm bean wiring, transaction hay database, có test integration khác.

**Các kết quả trong bài là expected assertions từ source code, không phải tuyên bố đã thực chạy Gradle hoặc test suite trong lúc biên soạn.**

## 2. Tách đặc tả khỏi code trước khi viết test

Một quy tắc cần được viết thành hợp đồng đo được. Nếu thiếu hợp đồng, developer có thể tạo test khớp với lỗi implementation mà không biết.

| Quy tắc | Đầu vào hoặc biên | Kỳ vọng |
| --- | --- | --- |
| SKU | null, rỗng, whitespace | IllegalArgumentException |
| SKU | Sau trim + uppercase không match định dạng | IllegalArgumentException |
| SKU | " abc-123 " | Chuẩn hóa thành ABC-123 |
| Quantity | 0, âm, 21 | IllegalArgumentException |
| Quantity | 1 hoặc 20 | Hợp lệ |
| Unit price | null, 0, âm | IllegalArgumentException |
| Unit price | 0.01 hoặc 10000.00 | Hợp lệ |
| Unit price | 10000.01 | IllegalArgumentException |
| Unit price | 1.234 | IllegalArgumentException do không thể ghi chính xác hai chữ số |
| Unit price | 10.000 | Hợp lệ, vì có thể rút về 10.00 mà không làm tròn |
| Coupon | null, rỗng, blank | Không áp coupon |
| Coupon | Mã lạ | InvalidCouponException |
| Coupon | SAVE10 và subtotal 99.99 | CouponNotApplicableException |
| Coupon | SAVE10 và subtotal 100.00 | Giảm 10.00 |
| Discount | 100.05 × 10% = 10.005 | Làm tròn HALF_UP thành 10.01 |
| Stock | available âm | InventoryUnavailableException |
| Stock | available = quantity − 1 | InsufficientStockException |
| Stock | available = quantity | Hợp lệ |
| Shipping | Net 199.99 | Phí 12.00 |
| Shipping | Net 200.00 | Miễn phí |
| Shipping | Net 200.01 | Miễn phí |
| Total | Mọi báo giá hợp lệ | subtotal − discount + shipping |

**Quan trọng:** Coupon eligibility dựa trên **subtotal trước giảm**, nhưng shipping threshold dựa trên **net sau giảm**. Ví dụ subtotal 200.00, coupon SAVE10 giảm 20.00, net 180.00; đơn này **vẫn phải trả phí giao hàng 12.00**, tổng thanh toán 192.00. Đây là một nhánh dễ bị triển khai nhầm nếu kiểm ngưỡng shipping trước khi giảm giá.

### Thứ tự xử lý là một phần hợp đồng

~~~text
Request không null
    |
    v
Validate + normalize SKU
    |
    v
Validate quantity
    |
    v
Validate monetary unit price
    |
    v
Normalize coupon; validate coupon + subtotal threshold
    |
    v
InventoryPort.availableUnits(normalizedSku)
    |
    +-- negative available? -> InventoryUnavailableException
    |
    +-- less than requested? -> InsufficientStockException
    |
    v
Discount / net / shipping / total
    |
    v
PriceQuote immutable result
~~~

Cần kiểm **verifyNoInteractions(inventory)** đối với lỗi đầu vào hoặc coupon: một request đã không hợp lệ không nên gọi DB/remote inventory không cần thiết. Với request hợp lệ, nên assert gọi **đúng một lần với SKU đã chuẩn hóa**.

## 3. Lựa chọn kỹ thuật unit test

**JUnit Jupiter** cung cấp @Test, @ParameterizedTest, @MethodSource, @ValueSource, assertAll, assertEquals, assertThrowsExactly và lifecycle callbacks. **Mockito** tạo mock outbound port để đặt stock level hoặc chủ động ném exception. **MockitoExtension** tích hợp mock lifecycle và strict stubbing phù hợp.

Unit test nên:
- Tạo service bằng constructor, không dùng @SpringBootTest.
- Không mock chính class đang kiểm thử.
- Mock **InventoryPort**, không mock BigDecimal, records hay policy implementation.
- Có positive/negative controls, nhất là tại threshold.
- Dùng inputs mô tả rõ kịch bản; tránh random và network trong bộ test deterministic.
- So sánh số tiền bằng BigDecimal chuẩn hóa về scale 2, không dùng double.
- Assert loại exception đúng và dữ liệu đi kèm khi exception có fields.
- Verify không có call tới dependency ở nhánh validation lỗi.
- Đặt tên test diễn đạt **hành vi** thay vì tên method mơ hồ như test1, test2.
- Dùng parameterized tests khi nhiều trường hợp có cùng structure; giữ test độc lập cho một chính sách quan trọng hoặc một exception branch.

### Unit test khác integration test ở đâu?

Unit test không chứng minh Spring component scanning, @Transactional, database migration, API security hoặc repository queries. Một unit test quote service chạy đúng trong JVM chỉ chứng minh thuật toán và tương tác với **port giả lập** theo hợp đồng.

Khi dùng Spring Boot, kiến trúc sạch có thể giữ logic nghiệp vụ là Java thuần và tích hợp nó qua @Bean hoặc @Service + InventoryPort adapter thực ở layer khác. Sau đó bổ sung:
- @SpringBootTest khi cần kiểm wiring, profiles, transaction/proxy;
- @DataJpaTest để kiểm query persistence;
- @WebMvcTest/MockMvc để kiểm mapping/validation HTTP;
- Testcontainers integration để kiểm database thật.

**Không biến unit tests thành Spring integration tests chỉ vì project dùng Spring Boot.** Chạy cả context cho nhánh BigDecimal sẽ tăng thời gian và đôi khi che lỗi bằng fixtures phức tạp.

## 4. Project hoàn chỉnh Java 17 / Spring Boot 3.4.5

### 4.1. Cây tệp

~~~text
settings.gradle
build.gradle
src/main/java/com/example/quoteqa/QuoteQaApplication.java
src/main/java/com/example/quoteqa/QuoteRequest.java
src/main/java/com/example/quoteqa/PriceQuote.java
src/main/java/com/example/quoteqa/InventoryPort.java
src/main/java/com/example/quoteqa/OrderQuoteService.java
src/test/java/com/example/quoteqa/OrderQuoteServiceTest.java
~~~

Bộ project được thiết kế để **compile với Java 17**, dùng Spring Boot dependency management cho JUnit/Mockito. Class OrderQuoteService là Java domain service không annotate @Service trong demo; Spring Boot application class chỉ là entry point. Đây không phải một web API. Có thể chạy trực tiếp Gradle test để thực hành; không cần Docker, database hay HTTP server.

### 4.2. settings.gradle

~~~groovy
rootProject.name = 'unit-branch-boundary-quote'
~~~

### 4.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter-test** cung cấp JUnit Jupiter, Mockito và các thư viện assertion phổ biến. Không cần @SpringBootTest, spring-boot-starter-web hay database driver vì subject under test thuần Java. Trong Spring Boot 3.4, MockitoExtension thuộc Mockito JUnit Jupiter integration có trong test starter.

### 4.4. QuoteQaApplication.java

~~~java
package com.example.quoteqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteQaApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteQaApplication.class, args);
    }
}
~~~

Đây chỉ là application entry point để project đúng cấu trúc Spring Boot. **OrderQuoteService không được inject vào một Spring bean** trong demo, vì nhiệm vụ chính là unit test chính sách độc lập. Nếu ứng dụng thực đăng ký service làm bean, cấu hình InventoryPort adapter tương ứng và thêm wiring test riêng.

### 4.5. QuoteRequest.java

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;

public record QuoteRequest(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        String couponCode) {
}
~~~

Record gom toàn bộ inputs. Cố ý không validate ở canonical constructor: **OrderQuoteService** kiểm và chuẩn hóa inputs theo đúng thứ tự hợp đồng. Nhờ vậy unit test có thể tạo request lỗi rồi assert service từ chối. Trong API thực, có thể thêm validation ở transport layer, nhưng vẫn cần domain invariants khi service được gọi ngoài HTTP.

### 4.6. PriceQuote.java

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;

public record PriceQuote(
        String normalizedSku,
        int quantity,
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal shipping,
        BigDecimal total) {
}
~~~

Record immutable chứa kết quả tài chính. Mọi BigDecimal monetary fields được service trả với **scale = 2**. Đặt tên **normalizedSku** để phân biệt raw request SKU và giá trị đã dùng khi gọi inventory.

### 4.7. InventoryPort.java

~~~java
package com.example.quoteqa;

@FunctionalInterface
public interface InventoryPort {

    int availableUnits(String normalizedSku);
}
~~~

Đây là outbound dependency duy nhất. Production adapter có thể gọi repository/API, nhưng unit test chỉ cần Mockito mock hoặc lambda fake. Hợp đồng trong demo: số >=0 là tồn kho hợp lệ, số âm thể hiện dữ liệu inventory không hợp lệ. Adapter có thể ném InventoryUnavailableException nếu upstream/database lỗi; service không swallow exception thành báo giá giả.

## 5. OrderQuoteService: chính sách nghiệp vụ thực

**src/main/java/com/example/quoteqa/OrderQuoteService.java**

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public final class OrderQuoteService {

    private static final BigDecimal MIN_UNIT =
        new BigDecimal("0.01");
    private static final BigDecimal MAX_UNIT =
        new BigDecimal("10000.00");
    private static final BigDecimal MIN_COUPON_SUBTOTAL =
        new BigDecimal("100.00");
    private static final BigDecimal FREE_SHIPPING_AT =
        new BigDecimal("200.00");
    private static final BigDecimal SHIPPING_FEE =
        new BigDecimal("12.00");
    private static final BigDecimal TEN_PERCENT =
        new BigDecimal("0.10");
    private static final BigDecimal ZERO =
        new BigDecimal("0.00");

    private final InventoryPort inventory;

    public OrderQuoteService(InventoryPort inventory) {
        this.inventory = Objects.requireNonNull(
            inventory, "inventory");
    }

    public PriceQuote quote(QuoteRequest request) {
        Objects.requireNonNull(request, "request");

        String sku = normalizeSku(request.sku());
        int quantity = validateQuantity(request.quantity());
        BigDecimal unitPrice =
            validateUnitPrice(request.unitPrice());

        String coupon = normalizeCoupon(
            request.couponCode());
        BigDecimal subtotal = unitPrice
            .multiply(BigDecimal.valueOf(quantity))
            .setScale(2, RoundingMode.UNNECESSARY);

        BigDecimal discount = ZERO;

        if (coupon != null) {
            if (subtotal.compareTo(
                    MIN_COUPON_SUBTOTAL) < 0) {
                throw new CouponNotApplicableException(
                    "SAVE10 requires subtotal >= 100.00");
            }

            discount = subtotal
                .multiply(TEN_PERCENT)
                .setScale(2, RoundingMode.HALF_UP);
        }

        int available = inventory.availableUnits(sku);

        if (available < 0) {
            throw new InventoryUnavailableException(
                "inventory returned negative availability");
        }
        if (available < quantity) {
            throw new InsufficientStockException(
                quantity, available);
        }

        BigDecimal net = subtotal.subtract(discount);
        BigDecimal shipping = net.compareTo(
                FREE_SHIPPING_AT) >= 0
            ? ZERO
            : SHIPPING_FEE;

        BigDecimal total = net.add(shipping);

        return new PriceQuote(
            sku, quantity, subtotal,
            discount, shipping, total);
    }

    private static String normalizeSku(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "sku is required");
        }

        String normalized = raw
            .trim()
            .toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z0-9-]{3,16}")) {
            throw new IllegalArgumentException(
                "sku format is invalid");
        }
        return normalized;
    }

    private static int validateQuantity(int quantity) {
        if (quantity < 1 || quantity > 20) {
            throw new IllegalArgumentException(
                "quantity must be between 1 and 20");
        }
        return quantity;
    }

    private static BigDecimal validateUnitPrice(
            BigDecimal raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "unitPrice is required");
        }
        if (raw.compareTo(MIN_UNIT) < 0
                || raw.compareTo(MAX_UNIT) > 0) {
            throw new IllegalArgumentException(
                "unitPrice must be between 0.01 and 10000.00");
        }

        try {
            return raw.setScale(
                2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                "unitPrice must have exact cents",
                ex);
        }
    }

    private static String normalizeCoupon(
            String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }

        String normalized = raw.trim()
            .toUpperCase(Locale.ROOT);

        if (!"SAVE10".equals(normalized)) {
            throw new InvalidCouponException(
                "unknown coupon: " + normalized);
        }
        return normalized;
    }

    public static final class InvalidCouponException
            extends IllegalArgumentException {

        public InvalidCouponException(String message) {
            super(message);
        }
    }

    public static final class CouponNotApplicableException
            extends IllegalArgumentException {

        public CouponNotApplicableException(String message) {
            super(message);
        }
    }

    public static final class InventoryUnavailableException
            extends IllegalStateException {

        public InventoryUnavailableException(String message) {
            super(message);
        }
    }

    public static final class InsufficientStockException
            extends IllegalStateException {

        private final int requested;
        private final int available;

        public InsufficientStockException(
                int requested, int available) {
            super("insufficient stock: requested="
                + requested + ", available=" + available);
            this.requested = requested;
            this.available = available;
        }

        public int getRequested() {
            return requested;
        }

        public int getAvailable() {
            return available;
        }
    }
}
~~~

### 5.1. Điều gì quan trọng trong implementation?

**Objects.requireNonNull(request)**: null request có một hợp đồng riêng, ném NullPointerException rõ tham số. Không để NPE tình cờ phát sinh sâu trong service khi gọi request.sku().

**normalizeSku**: bỏ spaces hai đầu và uppercase với Locale.ROOT. SKU không được null và phải match ký tự/dài hợp lệ. Gửi chính normalized SKU tới inventory; test cần verify exact argument.

**validateQuantity**: chấp nhận 1 và 20, từ chối 0 và 21. Câu điều kiện có **>= / <=** tương đương rõ với min/max contract. Test cả ngay dưới, tại, ngay trên để bắt mutation đổi inclusive thành exclusive.

**validateUnitPrice**: giá được so với Min/Max bằng **BigDecimal.compareTo**, không dùng double. **setScale(2, RoundingMode.UNNECESSARY)** chấp nhận 10.000 vì có thể biểu diễn chính xác 10.00, nhưng từ chối 1.234 vì buộc phải làm tròn. Với đầu vào giá, silent rounding là sai: nếu caller gửi 1.234, service yêu cầu sửa dữ liệu thay vì âm thầm cắt/round.

**normalizeCoupon**: null/blank là không coupon. Các mã lạ bị từ chối **trước inventory call**. Mã SAVE10 chỉ áp dụng khi subtotal trước discount >=100.00.

**Coupon discount**: dùng BigDecimal("0.10"), HALF_UP tại hai chữ số; ví dụ 100.05 ×0.10 =10.005 →10.01. Không dùng float/double.

**Inventory check**: sau khi validation xong mới gọi outbound port. Số âm bị xem là bất thường, tồn kho bằng chính quantity được chấp nhận, thiếu một đơn vị ném InsufficientStockException với requested/available để người gọi phân tích.

**Shipping**: dựa trên **net sau coupon**, không phải subtotal trước coupon. Net >=200.00 miễn phí; net thấp hơn trả 12.00. Shipping không được tính trên total đã bao gồm shipping (tránh vòng lặp logic).

**PriceQuote**: trả fields có scale 2, không chứa side effect tạo order, reserve stock hoặc gửi message. Bài này tính báo giá, không thực hiện đặt hàng: nếu cần atomic reservation, phải có transaction/idempotency integration test riêng.

## 6. Unit test đầy đủ với JUnit Jupiter và Mockito

**src/test/java/com/example/quoteqa/OrderQuoteServiceTest.java**

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;
import java.util.stream.Stream;

import com.example.quoteqa.OrderQuoteService.CouponNotApplicableException;
import com.example.quoteqa.OrderQuoteService.InsufficientStockException;
import com.example.quoteqa.OrderQuoteService.InvalidCouponException;
import com.example.quoteqa.OrderQuoteService.InventoryUnavailableException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderQuoteServiceTest {

    @Mock
    private InventoryPort inventory;

    private OrderQuoteService service;

    @BeforeEach
    void setUp() {
        service = new OrderQuoteService(inventory);
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("validPricingCases")
    void calculatesQuoteAtImportantBoundaries(
            String caseName,
            String priceText,
            int quantity,
            String coupon,
            String expectedSubtotal,
            String expectedDiscount,
            String expectedShipping,
            String expectedTotal) {

        when(inventory.availableUnits("ABC-123"))
            .thenReturn(20);

        QuoteRequest input = new QuoteRequest(
            "ABC-123", quantity,
            new BigDecimal(priceText), coupon);

        PriceQuote result = service.quote(input);

        assertAll(caseName,
            () -> assertEquals("ABC-123",
                result.normalizedSku()),
            () -> assertEquals(quantity,
                result.quantity()),
            () -> assertEquals(
                new BigDecimal(expectedSubtotal),
                result.subtotal()),
            () -> assertEquals(
                new BigDecimal(expectedDiscount),
                result.discount()),
            () -> assertEquals(
                new BigDecimal(expectedShipping),
                result.shipping()),
            () -> assertEquals(
                new BigDecimal(expectedTotal),
                result.total()),
            () -> assertEquals(
                result.subtotal()
                    .subtract(result.discount())
                    .add(result.shipping()),
                result.total())
        );

        verify(inventory).availableUnits("ABC-123");
        verifyNoMoreInteractions(inventory);
    }

    static Stream<Arguments> validPricingCases() {
        return Stream.of(
            Arguments.of(
                "minimum accepted price",
                "0.01", 1, null,
                "0.01", "0.00", "12.00", "12.01"),
            Arguments.of(
                "small subtotal",
                "1.25", 3, null,
                "3.75", "0.00", "12.00", "15.75"),
            Arguments.of(
                "below shipping threshold",
                "199.99", 1, null,
                "199.99", "0.00", "12.00", "211.99"),
            Arguments.of(
                "exactly shipping threshold",
                "200.00", 1, null,
                "200.00", "0.00", "0.00", "200.00"),
            Arguments.of(
                "above shipping threshold",
                "200.01", 1, null,
                "200.01", "0.00", "0.00", "200.01"),
            Arguments.of(
                "coupon threshold exactly 100",
                "20.00", 5, "SAVE10",
                "100.00", "10.00", "12.00", "102.00"),
            Arguments.of(
                "half up discount rounding",
                "100.05", 1, "SAVE10",
                "100.05", "10.01", "12.00", "102.04"),
            Arguments.of(
                "coupon turns free shipping into paid",
                "200.00", 1, "SAVE10",
                "200.00", "20.00", "12.00", "192.00"),
            Arguments.of(
                "coupon net reaches 200 exactly",
                "222.22", 1, "SAVE10",
                "222.22", "22.22", "0.00", "200.00"),
            Arguments.of(
                "maximum quantity is allowed",
                "10.00", 20, null,
                "200.00", "0.00", "0.00", "200.00"),
            Arguments.of(
                "maximum accepted unit price",
                "10000.00", 1, null,
                "10000.00", "0.00", "0.00", "10000.00"),
            Arguments.of(
                "blank coupon means no coupon",
                "50.00", 2, "  ",
                "100.00", "0.00", "12.00", "112.00"),
            Arguments.of(
                "lowercase coupon accepted",
                "250.00", 1, "save10",
                "250.00", "25.00", "0.00", "225.00")
        );
    }

    @Test
    void normalizesSkuAndCouponBeforeInventoryCall() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(2);

        PriceQuote result = service.quote(
            new QuoteRequest(
                "  abc-123  ", 2,
                new BigDecimal("60.00"),
                "  save10  "));

        assertAll(
            () -> assertEquals(
                "ABC-123", result.normalizedSku()),
            () -> assertEquals(
                new BigDecimal("120.00"),
                result.subtotal()),
            () -> assertEquals(
                new BigDecimal("12.00"),
                result.discount()),
            () -> assertEquals(
                new BigDecimal("12.00"),
                result.shipping()),
            () -> assertEquals(
                new BigDecimal("120.00"),
                result.total())
        );
        verify(inventory).availableUnits("ABC-123");
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void rejectsNullRequestWithoutCallingInventory() {
        NullPointerException error =
            assertThrowsExactly(
                NullPointerException.class,
                () -> service.quote(null));

        assertEquals("request", error.getMessage());
        verifyNoInteractions(inventory);
    }

    @ParameterizedTest
    @MethodSource("invalidSkuCases")
    void rejectsInvalidSkuBeforeInventory(String sku) {
        QuoteRequest request = new QuoteRequest(
            sku, 1, new BigDecimal("10.00"), null);

        IllegalArgumentException error =
            assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(request));

        assertNotNull(error.getMessage());
        verifyNoInteractions(inventory);
    }

    static Stream<Arguments> invalidSkuCases() {
        return Stream.of(
            Arguments.of((Object) null),
            Arguments.of(""),
            Arguments.of("  "),
            Arguments.of("ab"),
            Arguments.of("a_b"),
            Arguments.of("ABC!123"),
            Arguments.of("ABCDEFGHIJKLMNOPQ")
        );
    }

    @ParameterizedTest
    @ValueSource(ints = {
        Integer.MIN_VALUE, -1, 0, 21, Integer.MAX_VALUE
    })
    void rejectsQuantityOutsideOneToTwenty(int quantity) {
        QuoteRequest request = new QuoteRequest(
            "ABC-123", quantity,
            new BigDecimal("10.00"), null);

        IllegalArgumentException error =
            assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(request));

        assertTrue(error.getMessage().contains("quantity"));
        verifyNoInteractions(inventory);
    }

    @ParameterizedTest
    @MethodSource("invalidUnitPriceCases")
    void rejectsInvalidUnitPriceBeforeInventory(
            BigDecimal price) {
        QuoteRequest request = new QuoteRequest(
            "ABC-123", 1, price, null);

        IllegalArgumentException error =
            assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(request));

        assertTrue(error.getMessage().contains("unitPrice"));
        verifyNoInteractions(inventory);
    }

    static Stream<Arguments> invalidUnitPriceCases() {
        return Stream.of(
            Arguments.of((Object) null),
            Arguments.of(new BigDecimal("-0.01")),
            Arguments.of(new BigDecimal("0.00")),
            Arguments.of(new BigDecimal("0.001")),
            Arguments.of(new BigDecimal("1.234")),
            Arguments.of(new BigDecimal("10000.01"))
        );
    }

    @Test
    void acceptsTrailingZeroesThatDoNotRequireRounding() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(1);

        PriceQuote result = service.quote(
            new QuoteRequest(
                "ABC-123", 1,
                new BigDecimal("10.000"), null));

        assertEquals(
            new BigDecimal("10.00"),
            result.subtotal());
        assertEquals(
            new BigDecimal("22.00"),
            result.total());

        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void unknownCouponFailsBeforeInventory() {
        InvalidCouponException error =
            assertThrowsExactly(
                InvalidCouponException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("150.00"),
                    "BOGUS")));

        assertTrue(error.getMessage().contains("BOGUS"));
        verifyNoInteractions(inventory);
    }

    @Test
    void couponAtOneCentBelowMinimumIsRejected() {
        CouponNotApplicableException error =
            assertThrowsExactly(
                CouponNotApplicableException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("99.99"),
                    "SAVE10")));

        assertTrue(error.getMessage().contains("100.00"));
        verifyNoInteractions(inventory);
    }

    @Test
    void stockEqualToRequestedQuantityIsAccepted() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(3);

        PriceQuote quote = service.quote(
            new QuoteRequest(
                "ABC-123", 3,
                new BigDecimal("10.00"), null));

        assertEquals(3, quote.quantity());
        assertEquals(
            new BigDecimal("42.00"), quote.total());
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void stockOneBelowRequestedIsRejected() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(2);

        InsufficientStockException error =
            assertThrowsExactly(
                InsufficientStockException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 3,
                    new BigDecimal("10.00"), null)));

        assertAll(
            () -> assertEquals(3, error.getRequested()),
            () -> assertEquals(2, error.getAvailable()),
            () -> assertTrue(error.getMessage()
                .contains("insufficient stock"))
        );
        verify(inventory).availableUnits("ABC-123");
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void zeroStockIsRejectedForPositiveQuantity() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(0);

        InsufficientStockException error =
            assertThrowsExactly(
                InsufficientStockException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("10.00"), null)));

        assertEquals(0, error.getAvailable());
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void negativeAvailabilityIsInfrastructureError() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(-1);

        InventoryUnavailableException error =
            assertThrowsExactly(
                InventoryUnavailableException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("10.00"), null)));

        assertTrue(error.getMessage()
            .contains("negative availability"));
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void inventoryPortFailurePropagatesUnchanged() {
        InventoryUnavailableException upstream =
            new InventoryUnavailableException(
                "inventory timeout");

        when(inventory.availableUnits("ABC-123"))
            .thenThrow(upstream);

        InventoryUnavailableException actual =
            assertThrowsExactly(
                InventoryUnavailableException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("10.00"), null)));

        assertSame(upstream, actual);
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void constructorRejectsMissingInventoryPort() {
        NullPointerException error =
            assertThrowsExactly(
                NullPointerException.class,
                () -> new OrderQuoteService(null));

        assertEquals("inventory", error.getMessage());
        verifyNoInteractions(inventory);
    }

    @Test
    void fakeCanTestCoreFormulaWithoutMockito() {
        InventoryPort fakeInventory = sku -> 20;
        OrderQuoteService policy =
            new OrderQuoteService(fakeInventory);

        PriceQuote result = policy.quote(
            new QuoteRequest(
                "ABC-123", 1,
                new BigDecimal("200.00"),
                "SAVE10"));

        assertAll(
            () -> assertEquals(
                new BigDecimal("200.00"),
                result.subtotal()),
            () -> assertEquals(
                new BigDecimal("20.00"),
                result.discount()),
            () -> assertEquals(
                new BigDecimal("12.00"),
                result.shipping()),
            () -> assertEquals(
                new BigDecimal("192.00"),
                result.total())
        );
    }
}
~~~

### 6.1. Tại sao dùng @ParameterizedTest và @MethodSource?

Những tình huống tính giá có cấu trúc giống nhau: tạo QuoteRequest, mock tồn kho đủ, gọi quote, so sánh sáu fields và một invariant. Dùng **@MethodSource** để cung cấp các **Arguments** có tên tình huống, giữ từng biên dễ đọc trong test report.

Bộ validPricingCases gồm:
- Giá tối thiểu 0.01.
- Tổng nhỏ có phí shipping.
- Net ngay **dưới**, **bằng**, **trên** mức miễn phí ship 200.00.
- Coupon hợp lệ tại mức **100.00** trước giảm.
- HALF_UP với **10.005 thành 10.01**.
- Coupon biến một đơn miễn ship thành đơn tính ship.
- Coupon đưa net chính xác 200.00.
- Quantity tại mức tối đa 20.
- Unit price tại mức tối đa 10000.00.
- Coupon blank không áp giảm.
- Coupon lowercase được chuẩn hóa.

Mỗi case assert **từng field BigDecimal** và **bất biến total = subtotal − discount + shipping**, rồi verify inventory đúng một lần. Chỉ assert total là chưa đủ: một bug trừ sai discount nhưng cộng shipping sai vẫn có thể vô tình tạo cùng total. Assert subtotal/discount/shipping riêng giúp phát hiện lỗi đúng nhánh.

### 6.2. Vì sao không chỉ một test happy path?

Một test giá 100, số lượng 1 không coupon sẽ không bắt được:
- quantity=0 hoặc 21 bị chấp nhận;
- shipping comparator từ >= thành >;
- coupon eligibility comparator từ >= thành >;
- discount được tính sau shipping;
- 10% dùng double gây sai rounding;
- inventory được gọi trước khi validate;
- không normalize SKU/coupon;
- thiếu hàng hoặc inventory timeout bị nuốt;
- coupon được tính sau khi đã miễn ship theo subtotal.

Boundary tests là cách **giết những mutation gần ngưỡng**. Không có code coverage percentage nào thay thế việc assert đúng hợp đồng từng nhánh.

### 6.3. assertThrowsExactly khác assertThrows thế nào?

**assertThrows(IllegalArgumentException.class, ...)** sẽ pass nếu exception thực tế là subclass của IllegalArgumentException. Với nhánh nghiệp vụ riêng như **InvalidCouponException** hay **CouponNotApplicableException**, **assertThrowsExactly** yêu cầu đúng class được ném, tránh test pass nhờ một exception không mong đợi cùng superclass.

Dùng assertThrows khi contract cố ý chấp nhận subtype; dùng assertThrowsExactly khi **loại cụ thể** là một phần API. Đừng chỉ assertThrows(Exception.class) hoặc catch Throwable rồi coi là test pass.

Với exception có dữ liệu, kiểm **requested**, **available**, message key hoặc cause. Tránh assert toàn bộ stack trace, line number, internal Mockito proxy class names hay locale-dependent wording không thuộc contract.

### 6.4. assertAll và BigDecimal

**assertAll** nhóm nhiều assertions cho một kết quả. Nếu một field sai, JUnit có thể báo nhiều lỗi cùng lúc thay vì dừng ở field đầu tiên. Đây là lợi ích cho báo giá có nhiều field.

**new BigDecimal("10.00")** và **new BigDecimal("10.0")** có giá trị số học bằng nhau nhưng BigDecimal.equals yêu cầu scale cũng bằng nhau. Trong demo, service trả **scale 2**, nên assertEquals(BigDecimal("10.00"), result) vừa kiểm **value** vừa kiểm contract scale. Nếu business chỉ cần số học, dùng compareTo hoặc AssertJ isEqualByComparingTo; hãy chọn có chủ đích, đừng để scale difference là bug giả.

**Không dùng BigDecimal(double)** để khởi tạo số tiền hay dùng equals giữa BigDecimals có scale tùy ý. HALF_UP ở đây là chính sách minh họa; tiền/tax ở hệ thống thật có thể cần currency-specific rounding rules, tax jurisdiction và Money object.

### 6.5. verifyNoInteractions bảo vệ điều gì?

Một request có quantity=0 hoặc coupon lạ có thể được từ chối ngay mà không mất network/database call. **verifyNoInteractions(inventory)** khẳng định điều ấy. Nếu implementation bị sửa để gọi inventory trước validation, test sẽ fail ngay cả khi exception vẫn đúng.

Lưu ý: **verifyNoInteractions không chứng minh không có side effect ở ngoài mock** (ví dụ ghi file hoặc gọi static global state). Cần thiết kế service chỉ tương tác qua ports có thể quan sát, hoặc bổ sung integration test cho effects thật. Không mock mọi dependency chỉ để verify số calls, vì test sẽ trở nên implementation-specific.

### 6.6. Khi nào verifyNoMoreInteractions là quá chặt?

Với một **command** mà hợp đồng yêu cầu inventory chỉ được tra đúng một lần vì chi phí/consistency, verifyNoMoreInteractions hợp lý. Nhưng nếu implementation được phép cache, prefetch hoặc batch, việc test cứng số lần gọi có thể ràng buộc internal optimization không quan trọng. Hãy verify only những interactions thuộc contract, không bắt mọi method call của các helper nội bộ.

Ở đây InventoryPort đơn giản có một method; kiểm một lần phù hợp với yêu cầu tránh query thừa và tránh side effects.

## 7. Đọc ma trận biên: dưới – tại – trên

### 7.1. Số lượng

| Quantity | Tình huống | Kỳ vọng |
| --- | --- | --- |
| -1 | Dưới min | IllegalArgumentException |
| 0 | Ngay dưới min | IllegalArgumentException |
| 1 | Min hợp lệ | Quote thành công |
| 20 | Max hợp lệ | Quote thành công nếu kho đủ |
| 21 | Ngay trên max | IllegalArgumentException |
| Integer.MAX_VALUE | Out-of-range cực đại | IllegalArgumentException |

Số lượng âm và 0 đều không hợp lệ. Chính **1 và 20** bắt được lỗi đổi comparator từ >= thành > hoặc <= thành <. Không cần chạy mọi số nguyên trong range để chứng minh điều kiện biên; bổ sung vài representative middle values và invariant tests là đủ cho quy tắc đơn giản.

### 7.2. Giá trị tiền

| Unit price | Kỳ vọng | Lý do |
| --- | --- | --- |
| null | Error | Required |
| -0.01 | Error | Negative |
| 0.00 | Error | Below minimum |
| 0.001 | Error | Below minimum |
| 0.01 | Success | Exact lower bound |
| 1.234 | Error | Requires rounding to cents |
| 10.000 | Success, normalized 10.00 | Extra trailing zeroes exact |
| 10000.00 | Success | Exact upper bound |
| 10000.01 | Error | Above max |

Unit price có max để business bảo vệ dữ liệu phi lý; quantity có max nên subtotal có thể lớn hơn max unit price mà vẫn hợp lệ. **Không áp max unit price cho subtotal** một cách nhầm lẫn.

### 7.3. Coupon threshold

| Subtotal trước discount | Coupon | Kỳ vọng |
| --- | --- | --- |
| 99.99 | SAVE10 | CouponNotApplicableException |
| 100.00 | SAVE10 | Discount 10.00 |
| 100.05 | SAVE10 | Discount 10.01, HALF_UP |
| 200.00 | SAVE10 | Discount 20.00, net180.00 |
| 222.22 | SAVE10 | Discount22.22, net200.00 |
| 50.00 | null | No discount |
| 50.00 | unknown | InvalidCouponException |

**Nên có negative case ngay dưới 100.00 và positive case đúng 100.00.** Nếu implementation dùng > thay vì >=, cặp này sẽ bắt được. Cũng cần một unknown coupon test để phân biệt invalid code với valid but ineligible code.

### 7.4. Shipping threshold theo net sau discount

| Subtotal | Discount | Net | Shipping |
| --- | --- | --- | --- |
| 199.99 | 0.00 | 199.99 | 12.00 |
| 200.00 | 0.00 | 200.00 | 0.00 |
| 200.01 | 0.00 | 200.01 | 0.00 |
| 200.00 | 20.00 | 180.00 | 12.00 |
| 222.22 | 22.22 | 200.00 | 0.00 |

Không suy “subtotal >=200 nên shipping miễn phí” khi coupon đã làm net giảm xuống dưới threshold. Đó là nhánh kết hợp giữa discount và shipping, thường ít được cover bởi tests chỉ kiểm từng rule riêng lẻ.

### 7.5. Tồn kho

| Available | Quantity | Kỳ vọng |
| --- | --- | --- |
| -1 | 1 | InventoryUnavailableException |
| 0 | 1 | InsufficientStockException |
| 2 | 3 | InsufficientStockException(requested=3, available=2) |
| 3 | 3 | Success |
| 4 | 3 | Success |
| InventoryPort throws | 1 | Exception propagate theo policy |

**Mỗi boundary khác nhau có semantics khác.** Available=-1 không nên được hiểu như chỉ thiếu một hàng; nó biểu diễn inventory adapter/response không hợp lệ, cần điều tra. Với production adapter, thường tốt hơn ném exception typed khi upstream hỏng thay vì dùng negative sentinel; unit test demo vẫn kiểm cả invariant của port.

## 8. Thiết kế test độc lập, lặp lại được

### Không dùng @SpringBootTest cho domain unit test

Một test quote service không cần Spring IoC, HTTP server, JPA, Kafka hoặc @Transactional. Annotation **@SpringBootTest** sẽ tạo ApplicationContext có thể bao gồm nhiều configurations và external dependencies không liên quan, làm test chậm và flakier. Dùng:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderQuoteServiceTest {
    @Mock InventoryPort inventory;
    OrderQuoteService service;

    @BeforeEach
    void setUp() {
        service = new OrderQuoteService(inventory);
    }
}
~~~

Bộ test chạy bằng JUnit 5 + Mockito. MockitoExtension tạo/điều hành mock và strict stubbing. Không dùng MockitoAnnotations.openMocks thủ công cùng MockitoExtension nếu không cần, vì dễ tạo lifecycle chồng nhau hoặc close resources sai.

### Không sử dụng đồng hồ, mạng hoặc random trong test

Báo giá cố định theo QuoteRequest và InventoryPort response. Các bài thực tế có expiration time hoặc FX rate nên inject **Clock**, **ExchangeRatePort**, **TaxPolicy** theo contract và fake chúng. Nếu test gọi Instant.now hoặc remote rate API thật, nó không còn deterministic. Một unit test có thể chạy cùng seed data nhiều lần với cùng kết quả.

### Để test fail khi implementation sai

Một test chỉ có:

~~~java
assertNotNull(service.quote(validRequest));
~~~

sẽ pass ngay cả khi discount/shipping/total sai. Tốt hơn assert exact fields, exception types, boundary behavior và relevant port interactions. Test data phải tạo khả năng phân biệt hai nhánh, không chỉ lấy một con số mà cả hai nhánh trùng kết quả.

### Không kiểm nội bộ không thuộc contract

Đừng dùng reflection để xem private MIN_COUPON_SUBTOTAL constant hoặc verify private method. Test **observable public behavior** từ quote() thay vì implementation detail. Việc đổi helper methods hoặc refactor code không nên làm test fail nếu behavior không đổi.

### Unit tests không kiểm reservation race

Quote method chỉ **đọc availableUnits**, không reserve stock atomically. Hai orders đồng thời có thể cùng báo đủ hàng; đó là concern của order placement/reservation. Test integration nên kiểm transaction/isolation/optimistic locking nếu nghiệp vụ cần giữ hàng. Không mô tả unit test này như bằng chứng concurrent order safety.

## 9. Bảo vệ nhánh lỗi bằng exact exceptions

### Invalid input là IllegalArgumentException

- SKU sai format.
- Quantity ngoài 1..20.
- Unit price null/out-of-range/precision invalid.

Các lỗi này xảy ra trước InventoryPort. Test assertThrowsExactly(IllegalArgumentException.class) và verifyNoInteractions.

### InvalidCouponException khác CouponNotApplicableException

- Unknown code: **InvalidCouponException**.
- SAVE10 đúng tên nhưng subtotal dưới 100.00: **CouponNotApplicableException**.

Cả hai extends IllegalArgumentException, nhưng user/business error mapping có thể khác (ví dụ INVALID_COUPON vs COUPON_MINIMUM_NOT_MET). Vì vậy unit tests yêu cầu exact subclasses thay vì chỉ IllegalArgumentException chung.

### InsufficientStockException và InventoryUnavailableException

- Kho trả 2 khi đặt3: **InsufficientStockException**, có requested/available.
- Kho trả -1: **InventoryUnavailableException**, không phải low-stock state.
- Adapter ném InventoryUnavailableException: **propagate unchanged** theo code.

Không trả PriceQuote tổng 0 khi inventory unavailable: đó là fail-open dễ che lỗi hoặc tạo quyết định thanh toán sai. Nếu product muốn fallback cache stock, phải thiết kế policy rõ và có tests cho stale-data semantics; không tự suy diễn từ demo.

## 10. Ghi nhận coverage mà không đánh đồng chất lượng

**Line coverage** cho biết bao nhiêu dòng được thực thi. **Branch coverage** giúp biết điều kiện true/false đã đi qua hay chưa. Nhưng ngay cả branch coverage cao vẫn có thể thiếu assertions mạnh.

Ví dụ:

~~~java
if (net.compareTo(FREE_SHIPPING_AT) >= 0) {
    shipping = ZERO;
}
~~~

Một test net=250 và một test net=50 có thể cover hai nhánh nhưng **không bắt mutation >= thành >**. Bổ sung test net=200 chính xác. Tương tự:
- Quantity=1 và20 để kiểm inclusive ends.
- Coupon subtotal=99.99 và100.00.
- Stock available=quantity-1 và quantity.
- Discount 10.005 để bắt đổi HALF_UP thành HALF_EVEN hoặc DOWN trong tình huống phù hợp.
- UNKNOWN coupon và valid-but-ineligible coupon để bắt exception branch merge.

**Mutation testing** (ví dụ PIT cho Java) cố ý thay operators/constants để đo xem tests có phát hiện lỗi không. Đây là công cụ bổ sung, không thay business spec. Một test có thể kill mutation nhưng vẫn viết wrong expected behavior nếu đặc tả ban đầu sai. Ưu tiên review nghiệp vụ và chọn mẫu ranh giới có ý nghĩa.

### Data tables là bằng chứng, không là dữ liệu ngẫu nhiên

@MethodSource mô tả rõ caseName, price, quantity, coupon và expected numbers. Test report tự thể hiện kịch bản nào fail. Dùng test data ngắn và có tính phân biệt; tránh random 1000 trường hợp không thể debug khi fail. Nếu cần property-based testing, chọn jqwik/QuickTheories với fixed seeds, shrinking và các invariants xác định; vẫn giữ example-based boundary tests.

## 11. Kỹ thuật assertAll, assertThrowsExactly và Mockito

### Assert all fields, nhưng tránh assert phụ thuộc lẫn nhau

Bộ code assert các expected fields bằng literals độc lập. Nó còn assert **subtotal - discount + shipping = total**. Invariant hữu ích nhưng nếu test chỉ so hai giá trị do cùng implementation sai tạo ra thì có thể không phát hiện lỗi. Vì vậy cần có cả exact expected numbers từ business spec.

### Kiểm được exception, nguyên nhân và message

~~~java
InsufficientStockException error =
    assertThrowsExactly(
        InsufficientStockException.class,
        () -> service.quote(request));

assertAll(
    () -> assertEquals(3, error.getRequested()),
    () -> assertEquals(2, error.getAvailable())
);
~~~

Đây là snippet minh họa bên trong test. Nội dung error message có thể thay đổi theo ngôn ngữ hoặc refactor; ưu tiên code/type/structured fields thuộc contract thay vì so full tiếng Anh sentence khi không yêu cầu.

### Kiểm không gọi cổng ở nhánh lỗi

~~~java
assertThrowsExactly(
    IllegalArgumentException.class,
    () -> service.quote(badRequest));

verifyNoInteractions(inventory);
~~~

Đây là assertion quan trọng về thứ tự validation. Với positive case:

~~~java
verify(inventory).availableUnits("ABC-123");
verifyNoMoreInteractions(inventory);
~~~

Các verify nên gắn với contract thực: chuẩn hóa SKU và số query. Nếu business thay đổi cho phép batch checks hoặc refresh cache, update test spec trước khi refactor, không biến mọi chi tiết nội bộ thành assertion cứng.

### @ParameterizedTest không phải tự động có isolation của Spring context

JUnit Jupiter mặc định PER_METHOD tạo test instance mới cho mỗi invocation theo lifecycle; MockitoExtension khởi mock mới phù hợp. Tuy vậy static mutable state hay system properties vẫn có thể rò giữa test cases. Đừng dùng static inventory map rồi để các cases thay đổi nó nếu không reset. Parameterized tests vẫn cần deterministic cases và mỗi invocation độc lập.

## 12. Kiểm thử thứ tự ưu tiên validation

Khi input có nhiều lỗi đồng thời, service hiện có thứ tự:
1. request null;
2. SKU format;
3. quantity range;
4. unitPrice range/precision;
5. coupon unknown/ineligible;
6. inventory availability.

Nếu test cần quy định **lỗi nào ưu tiên**, có thể thêm contract:
- Unknown coupon + stock unavailable → coupon error trước và no inventory call.
- Quantity=0 + coupon invalid → quantity error trước.
- Unit price invalid + missing stock → price error trước.

Không mặc định mọi service phải có thứ tự validation giống demo. Thứ tự chỉ là contract nếu được thống nhất với product và được phản ánh trong API error response. Tối thiểu, ta vẫn cần đảm bảo **invalid request không gọi outbound port**, vì đó là hiệu quả và an toàn. Service hiện tại làm đúng điều này.

Trong integration API, Bean Validation tại controller có thể reject sớm hơn domain validation. Đó là một lớp khác; unit test OrderQuoteService vẫn quan trọng vì service có thể được gọi từ scheduler, message consumer hoặc service khác không đi qua HTTP.

## 13. Khi kết hợp với Spring Boot thật

Đưa policy vào Spring context thường cần một adapter implement InventoryPort:

~~~java
@Configuration(proxyBeanMethods = false)
class QuoteWiring {

    @Bean
    OrderQuoteService orderQuoteService(
            InventoryPort inventoryPort) {
        return new OrderQuoteService(inventoryPort);
    }
}
~~~

Đây **chỉ là snippet định hướng tích hợp**, không thuộc runnable tree hiện tại vì chưa có InventoryPort adapter bean. Khi thêm adapter thật (JPA, JDBC hoặc HTTP client), cần:
- @SpringBootTest kiểm bean registration và dependency injection;
- Repository/JPA integration test kiểm dữ liệu/hợp đồng truy vấn;
- HTTP/MVC test kiểm request validation và status mapping từ exception;
- Transaction test kiểm stock reserve nếu order placement có side effects;
- Testcontainers để kiểm database dialect/constraints thật khi relevant.

Nếu một @SpringBootTest contextLoads pass, nó không chứng minh coupon threshold, HALF_UP hay stock boundary đúng. Unit tests là lớp bằng chứng riêng, chạy rất nhanh, nên CI có thể execute thường xuyên.

### Tách Quote vs PlaceOrder

Báo giá **không giảm tồn kho**. Production PlaceOrder có thể cần:
- lưu order trong transaction;
- kiểm lock/version tồn kho;
- idempotency key để tránh double-charge;
- validate pricing consistency;
- external payment timeout handling;
- outbox/event publishing.

Những điểm này là integration/contract tests khác. Đừng mock InventoryPort rồi tuyên bố stock đã được reserve atomically. Unit test nên không hứa điều mà implementation không thực hiện.

## 14. Những lỗi thực tế và cách tránh

| Anti-pattern | Hậu quả | Cách thay |
| --- | --- | --- |
| Chỉ test happy path 200.00 | Không bắt min/max lỗi | Under/at/over boundary |
| Chỉ line coverage, không assert money | Sai total vẫn pass | Assert exact fields + invariants |
| Dùng double cho tiền | Precision drift | BigDecimal(String), scale/round policy |
| Dùng == hoặc equals không hiểu scale | Sai money assertions | compareTo/value+scale contract |
| Tính shipping trước discount | Sai rule kết hợp | Test coupon đổi free→paid |
| Coupon threshold dùng > thay >= | Trượt đúng biên 100.00 | Test subtotal=100.00 |
| Free shipping threshold dùng > thay >= | Net200 vẫn tính ship | Test net=200.00 |
| Quantity=0 gọi inventory trước | Side effect không cần | verifyNoInteractions |
| Mock chính OrderQuoteService | Không thực thi rule | Service thật, mock InventoryPort |
| @SpringBootTest cho mọi branch test | Chậm, phụ thuộc context | Plain JUnit + Mockito |
| Test exception class chung | Che nhánh sai loại | assertThrowsExactly typed |
| Để default Mockito answer 0 rồi tưởng stock=0 fixture | Test pass nhầm | Explicit stub per scenario |
| verify tất cả helper calls | Brittle refactor | Verify contract-boundary effects |
| Random test cases không reproducible | Flaky | Table-driven deterministic |
| Dùng shared static inventory map | Cross-test contamination | Per-test fake/mock |
| Không tách invalid coupon và ineligible coupon | API error code sai | Two typed exceptions |
| Nuốt InventoryUnavailable rồi trả total0 | Fail-open nguy hiểm | Propagate typed failure |
| Biến quote thành stock reserve mà không transaction | Overselling | Integration/transaction tests |
| Assert full exception stacktrace | Brittle | Type + relevant structured details |
| Đặt test fixtures lớn với nhiều lỗi cùng lúc | Không biết nhánh nào thắng | One primary invalid condition per test |
| Hard-code timezone/locale mặc định | Môi trường CI khác | Explicit Locale/Clock khi cần |

## 15. Lệnh chạy và expected outcomes

Sau khi tạo đúng các files và có Gradle Wrapper tương thích Java 17:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest.calculatesQuoteAtImportantBoundaries
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest.couponAtOneCentBelowMinimumIsRejected
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest.stockOneBelowRequestedIsRejected
~~~

Trên Windows dùng **gradlew.bat**. Nếu chưa tạo Wrapper scripts trong project mới, dùng Gradle đã cài hoặc tạo Gradle wrapper trước; một build.gradle không tự cung cấp ./gradlew. **Không có log BUILD SUCCESSFUL được quan sát trong phiên soạn README**.

| Nhóm test | Kỳ vọng |
| --- | --- |
| validPricingCases | 13 mẫu hợp lệ, exact quote fields |
| normalizesSkuAndCouponBeforeInventoryCall | Normalized SKU/coupon; inventory called once |
| rejectsNullRequestWithoutCallingInventory | Exact NullPointerException; no interaction |
| rejectsInvalidSkuBeforeInventory | 7 invalid SKU cases; no interaction |
| rejectsQuantityOutsideOneToTwenty | 5 invalid quantities; no interaction |
| rejectsInvalidUnitPriceBeforeInventory | 6 invalid prices; no interaction |
| acceptsTrailingZeroesThatDoNotRequireRounding | 10.000 →10.00; total22.00 |
| unknownCouponFailsBeforeInventory | InvalidCouponException; no interaction |
| couponAtOneCentBelowMinimumIsRejected | CouponNotApplicableException |
| stockEqualToRequestedQuantityIsAccepted | available=quantity accepted |
| stockOneBelowRequestedIsRejected | InsufficientStockException(3,2) |
| zeroStockIsRejectedForPositiveQuantity | InsufficientStockException |
| negativeAvailabilityIsInfrastructureError | InventoryUnavailableException |
| inventoryPortFailurePropagatesUnchanged | Same exception instance propagated |
| constructorRejectsMissingInventoryPort | NullPointerException inventory |
| fakeCanTestCoreFormulaWithoutMockito | Quote net180 + ship12 = total192 |

JUnit @ParameterizedTest từ @MethodSource chạy một invocation cho mỗi row trong validPricingCases; @MethodSource invalid SKU/price và @ValueSource quantity mở rộng số test invocations. Không nên chỉ đếm Java @Test method annotations để báo tổng tests: mỗi parameterized case là một invocation riêng.

## 16. Bài tập mở rộng sau khi hoàn thành

**Bài tập A — kiểm coupon SAVE10 bị loại ở 99.99 nhưng chấp nhận 100.00.** Viết hai assertions độc lập. Tại sao 99.00 và 101.00 chưa đủ? Vì không bắt được sai dấu bằng ở threshold.

**Bài tập B — phép nhân và rounding.** Thử 100.05 ×10%=10.005 →10.01. Viết một test bắt mutation HALF_UP thành HALF_EVEN. Với 10.005, HALF_EVEN sẽ tạo 10.00, nên test chính xác 10.01 giúp phân biệt.

**Bài tập C — shipping.** Đưa subtotal=200.00 và SAVE10; expected total=192.00. Tại sao test chỉ giá 250.00 có thể không bắt? Vì sau giảm 225 vẫn miễn ship, không thấy nhánh chuyển free→paid.

**Bài tập D — normalization.** SKU raw " abc-123 " phải gọi inventory.availableUnits("ABC-123"), không gọi raw string. Coupon raw " save10 " phải áp 10%.

**Bài tập E — hiệu năng.** Test verifyNoInteractions cho invalid inputs; trong real adapter InventoryPort gọi DB, lợi ích là gì? Tránh request không hợp lệ tạo I/O, load và side effects.

**Bài tập F — thêm coupon SAVE20.** Mở rộng policy để coupon khác giảm20% với threshold riêng. Bổ sung exact-type exception tests, boundary tables, test unknown code và shipping after-discount. Không sao chép SAVE10 tests mà quên mức threshold mới.

**Bài tập G — tính thuế.** Nếu áp VAT, xác định base (trước/sau discount), rounding order, shipping taxability và currency policy trước khi viết code. Một test thiếu đặc tả không quyết định được kết quả đúng.

**Bài tập H — stock reservation.** Thêm PlaceOrderService với transaction; tạo integration tests cho concurrent requests và uniqueness/idempotency. Không cố chứng minh atomicity bằng verify(mock).availableUnits().

**Bài tập I — mutation testing.** Dùng PIT để kiểm mutation các toán tử >=/> và < /<= trên threshold. Chọn những mutation sống sót quan trọng, không chỉ chạy tool để tăng số phần trăm.

**Bài tập J — test report.** Đổi tên parameterized cases để người đọc báo cáo biết ngay biên nào sai. Không gộp tất cả cases vào một for-loop với failure message thiếu context.

## 17. Tự kiểm tra hiểu biết

**1.** Vì sao phải test quantity=0 và1? Vì min1 là inclusive; 0 phải fail, 1 phải pass.

**2.** Vì sao phải test quantity=20 và21? Vì max20 inclusive; 20 pass,21 fail.

**3.** Vì sao coupon subtotal=99.99 và100.00 quan trọng? Bắt toán tử sai ở ngưỡng.

**4.** Shipping dựa trên subtotal hay net? **Net sau discount** theo đặc tả demo.

**5.** Subtotal200, SAVE10 tạo total bao nhiêu? **192.00** (net180 +ship12).

**6.** Subtotal222.22, SAVE10 có free shipping không? **Có**, discount22.22 và net200.00.

**7.** Giá 10.000 có bị từ chối không? **Không**, có thể biểu diễn chính xác10.00.

**8.** Giá 1.234 có bị từ chối không? **Có**, phải làm tròn mới giữ 2 decimals.

**9.** Dùng double cho tiền có ổn không? **Không nên**, BigDecimal(String) và rounding policy rõ.

**10.** HALF_UP của 10.005 tới 2 decimals? **10.01**.

**11.** Vì sao test thông điệp exception cũng cần chọn lọc? Full sentence dễ thay đổi; type/structured data thường ổn định hơn.

**12.** assertThrowsExactly và assertThrows khác nhau? Exactly yêu cầu đúng class, assertThrows chấp nhận subtype.

**13.** assertAll có ích gì? Báo nhiều lỗi của cùng quote trong một invocation.

**14.** verifyNoInteractions cho invalid price chứng minh gì? Input validation không gọi inventory.

**15.** available=quantity−1 là gì? **InsufficientStockException**.

**16.** available=quantity là gì? **Success**, boundary của tồn kho.

**17.** available âm có được coi chỉ thiếu hàng? **Không**, service báo InventoryUnavailableException.

**18.** @SpringBootTest có cần cho pure price calculation? **Không**.

**19.** Có nên mock BigDecimal hay chính service? **Không**, dùng thật; mock outbound port.

**20.** @MethodSource làm gì? Cung cấp nhiều input/expected cases cho một parameterized test.

**21.** MockitoExtension giúp gì? Setup/teardown mocks và stubbing lifecycle cho JUnit Jupiter.

**22.** Một test 200.00 có bắt được coupon eligibility threshold100.00 không? **Chưa chắc**, cần đúng threshold100.00.

**23.** Unit test có chứng minh JPA query và transaction thực không? **Không**, cần integration tests.

**24.** Unit test quote có đảm bảo không oversell khi concurrent orders không? **Không**, quote không reserve stock.

**25.** Quy tắc cốt lõi? **Test observable behavior ở cả success và failure, ngay dưới/đúng/ngay trên ngưỡng, với assertions chính xác và không gọi side-effect port khi input invalid.**

### Checklist QA

- Đã viết đặc tả với inputs, threshold, rounding và error behavior trước code?
- Có test min/max inclusive và adjacent invalid values?
- Có assert exact discount, shipping và total với BigDecimal scale rõ?
- Có test coupon 99.99/100.00, shipping 199.99/200.00/200.01?
- Có test coupon làm một đơn miễn ship trở thành trả ship?
- Có test HALF_UP ở trường hợp đúng nửa-cent?
- Có test SKU/coupon normalization và exact port argument?
- Có test null request, SKU, quantity, price và unknown coupon?
- Có exact exception type cho InvalidCoupon, CouponNotApplicable, InsufficientStock và InventoryUnavailable?
- Có kiểm stock equal/one less/zero/negative/error from port?
- Invalid request có verifyNoInteractions(inventory)?
- Valid request có verify inventory đúng một lần?
- Có deterministic input, không đọc system clock/random/real network?
- Có dùng JUnit @ParameterizedTest/@MethodSource để bảng biên rõ?
- Có phân biệt unit test của domain policy với Spring integration/wiring test?
- Không mock class đang được kiểm thử hoặc assertion vào private internals?
- Không coi coverage percentage là thay thế strength của assertion?
- Không khẳng định đã chạy Gradle nếu chưa có runtime log?

**Kết luận:** Một unit test giá trị cao không chỉ chứng minh “giá ra đúng” cho một input đẹp. Nó phải xác nhận **các nhánh từ chối, điều kiện biên inclusive/exclusive, phép tính chính xác, side effects được kiểm soát và kết quả từng field đúng hợp đồng**. Với **JUnit Jupiter + Mockito**, giữ OrderQuoteService là subject thật, fake InventoryPort, dùng parameterized scenarios ở các ngưỡng và exception assertions có cấu trúc. Đây là nền tảng để kết hợp với các Spring Boot integration tests ở layer adapter/transaction/API khi cần bằng chứng rộng hơn.

## Tài liệu chính thức

- Spring Boot 3.4 — Test Scope Dependencies (JUnit 5, Mockito, AssertJ): https://docs.spring.io/spring-boot/3.4/reference/testing/test-scope-dependencies.html
- Spring Boot 3.4 — Testing: https://docs.spring.io/spring-boot/3.4/reference/testing/index.html
- JUnit Jupiter — Writing Tests, Assertions và Parameterized Tests: https://docs.junit.org/current/user-guide/
- JUnit 5 — Parameterized Tests / @MethodSource: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests-sources-MethodSource
- Mockito — MockitoExtension API: https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html
- Mockito — Verification API: https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html
- Java 17 — BigDecimal compareTo, setScale, RoundingMode: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java 17 — RoundingMode: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html
