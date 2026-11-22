# Phân biệt lỗi đầu vào với lỗi phụ thuộc hoặc trạng thái nghiệp vụ

Một yêu cầu không thành công có thể xuất phát từ nhiều nguyên nhân: khách hàng nhập sai dữ liệu, hệ thống phụ thuộc không phản hồi, hoặc dữ liệu hoàn toàn hợp lệ nhưng **trạng thái nghiệp vụ hiện tại không cho phép thực hiện**. Nếu gom tất cả vào một `IllegalArgumentException`, trả HTTP 400 cho mọi lỗi hoặc viết unit test chỉ mong “có exception”, ứng dụng sẽ khó xử lý, khó giám sát và dễ retry sai.

Trong Spring Boot, việc phân biệt nguyên nhân cần bắt đầu ở **hợp đồng nghiệp vụ và ranh giới phụ thuộc**, rồi mới chuyển thành HTTP status, log hoặc cơ chế retry tại lớp thích hợp. Unit test phải chứng minh **đúng loại lỗi, đúng điều kiện gây lỗi, không thực hiện side effect ngoài ý muốn** và không nhầm sự cố hệ thống với lỗi của người dùng.

## 1. Ba nhóm lỗi cần tách bạch

| Nhóm lỗi | Câu hỏi nhận diện | Ví dụ | Thường phải làm gì? |
|---|---|---|---|
| **Lỗi đầu vào** (*invalid input*) | Bản thân tham số/request có vi phạm hợp đồng trước khi cần biết trạng thái hệ thống không? | `quantity <= 0`, mã SKU rỗng, ngày kết thúc trước ngày bắt đầu | Báo rõ trường/rule sai; caller sửa dữ liệu trước khi gửi lại |
| **Lỗi trạng thái/quy tắc nghiệp vụ** (*business-state conflict*) | Dữ liệu có đúng định dạng nhưng hành động hiện không hợp lệ theo trạng thái thực tế không? | Hàng đã ngừng bán; kho chỉ còn 2 nhưng yêu cầu 5; đơn đã hủy nên không được thanh toán | Báo xung đột/từ chối theo nghiệp vụ; caller có thể đổi hành động, chọn tài nguyên khác hoặc chờ trạng thái đổi |
| **Lỗi phụ thuộc** (*dependency/infrastructure failure*) | Có một hệ thống/thiết bị/dịch vụ cần thiết thất bại khiến ta **chưa thể kết luận** yêu cầu hợp lệ hay không? | Catalog API timeout, DB mất kết nối, broker không khả dụng, upstream 503 | Ghi nhận sự cố; có thể retry có kiểm soát nếu an toàn, hoặc trả lỗi tạm thời và quan sát vận hành |

Một nhóm bổ sung cũng quan trọng: **bug/vi phạm hợp đồng nội bộ**, ví dụ `NullPointerException` do code sai, dữ liệu adapter trả không đúng giao kèo, phép tính tràn số hoặc exception bất ngờ. Không được tự động quy loại này thành “người dùng nhập sai”. Với tài nguyên không tồn tại, có thể có loại lỗi **not found** riêng; nó không đương nhiên là invalid input, nhất là khi định danh đúng cú pháp nhưng bản ghi không còn.

### Cùng một thông báo “không xử lý được” nhưng cách sửa khác nhau

- “Số lượng bằng 0”: người gọi sửa `quantity`; gửi lại nguyên request không giúp ích.
- “Số lượng 5 nhưng tồn kho 2”: request có cú pháp đúng; cần xử lý tình trạng kho hoặc đổi số lượng.
- “Không đọc được tồn kho vì catalog timeout”: **không biết** hiện có đủ hàng hay không; báo “hết hàng” ở thời điểm này là kết luận sai.

Như vậy, phân loại lỗi ảnh hưởng trực tiếp đến **thông báo cho người dùng, khả năng retry, HTTP contract, log/metrics và cách viết unit test**.

## 2. Đặt ranh giới phân loại đúng nơi

Một ứng dụng Spring Boot có thể có chuỗi:

```text
HTTP request
   │
   ▼
Controller + Bean Validation
   │  Kiểm tra shape: required, độ dài, kiểu, giới hạn đơn giản
   ▼
Application/Domain service
   │  Kiểm tra rule đầu vào gắn với use case
   │  Gọi port để đọc trạng thái cần thiết
   │  Kiểm tra invariant và trạng thái nghiệp vụ
   ▼
Repository / HTTP client / message broker adapter
   │  Chuyển timeout/transport/DB failure thành lỗi phụ thuộc có nghĩa
   ▼
Exception handler / API contract
      Chuyển từng nhóm lỗi thành response phù hợp
```

**Ranh giới 1: đầu vào.** Kiểm tra những điều có thể biết **trước khi I/O**. Controller dùng `@Valid`/`@NotBlank`/`@Positive` để phát hiện dữ liệu request không hợp lệ; service vẫn cần bảo vệ các bất biến quan trọng nếu nó còn được gọi từ message consumer, scheduled job hoặc một service khác. Không trói business service vào `HttpServletRequest` chỉ để biết lỗi thuộc nhóm nào.

**Ranh giới 2: trạng thái nghiệp vụ.** Cần dữ liệu đáng tin để ra quyết định. Chẳng hạn “sản phẩm inactive” chỉ là trạng thái hợp lệ của entity và rule không cho báo giá; “số lượng hàng tồn ít hơn yêu cầu” là xung đột với trạng thái kho. Một đơn hàng không thể từ CANCELLED quay lại PAID nếu state machine không cho phép. Lỗi trạng thái có thể thay đổi theo thời gian, khác với input sai vĩnh viễn.

**Ranh giới 3: phụ thuộc.** Adapter phải phân biệt **giao tiếp thất bại** với **phản hồi nghiệp vụ hợp lệ**. Timeout, kết nối bị từ chối, DNS/DB unavailable không được biến thành “không tìm thấy sản phẩm” hoặc “hết hàng”. Nếu upstream trả lời thành công nhưng cho biết sản phẩm inactive, đó là dữ liệu trạng thái để áp dụng business rule, không phải lỗi transport. Nếu upstream trả 409/422 với ý nghĩa nghiệp vụ được đặc tả trong hợp đồng, lớp adapter phải diễn giải theo contract, không mù quáng xem mọi non-2xx là lỗi mạng.

**Ranh giới 4: kết quả bên ngoài.** `@RestControllerAdvice` hoặc error mapper đưa exception sang HTTP contract. Lớp domain nên giữ nguyên ý nghĩa, tránh nhúng mã HTTP vào mọi class nghiệp vụ. Một mã status cụ thể là **quyết định API contract** chứ không phải tính chất cố định của mọi `IllegalStateException`.

## 3. Ma trận hành vi và kiểm thử cần có

| Tình huống | Lỗi/kết quả đúng | Điều unit test nên chứng minh |
|---|---|---|
| SKU `null`, rỗng hoặc chỉ whitespace | Invalid input | Đúng exception; **chưa gọi catalog** |
| Số lượng không dương | Invalid input | Đúng exception; **chưa gọi catalog** |
| SKU và số lượng hợp lệ, catalog trả sản phẩm active còn đủ hàng | Thành công | Đúng quote, đúng số lần gọi dependency |
| Sản phẩm đang inactive | Business state | Đúng exception xung đột trạng thái, không giả là timeout |
| Tồn kho nhỏ hơn số lượng yêu cầu | Business state | Đúng rule, không tạo kết quả quote |
| Catalog HTTP timeout hoặc mất kết nối | Dependency failure | Lỗi được truyền/ánh xạ đúng loại, không chuyển thành “SKU sai” hoặc “hết hàng” |
| SKU đúng cú pháp nhưng không có trong catalog | Not found riêng theo hợp đồng | Không tự đồng nhất với dữ liệu đầu vào sai định dạng |
| Input sai đồng thời catalog giả lập đang hỏng | Invalid input trước | Không gọi dependency; không che lỗi input bằng timeout |
| Adapter trả dữ liệu sai cấu trúc mà contract không cho phép | Contract/internal failure | Không gán nhầm lỗi cho caller; cần cảnh báo và test adapter |

Một phép thử kiểu `assertThrows(RuntimeException.class, ...)` thường quá yếu: invalid input, business conflict và timeout đều có thể là `RuntimeException`. Hãy dùng **kiểu exception cụ thể** và assertion về side effect/lời gọi dependency khi cần.

## 4. Ví dụ Java 17+ hoàn chỉnh: báo giá dựa trên catalog

Giả sử API nội bộ báo giá một SKU:

1. `sku` phải có nội dung và `quantity > 0`.
2. Catalog trả `Product` có trạng thái `active`, số lượng tồn `available` và `unitPriceVnd`.
3. Chỉ báo giá nếu sản phẩm active và tồn kho đủ; total bằng giá nhân số lượng.
4. Catalog có thể thất bại do timeout; tìm SKU hợp lệ nhưng không tồn tại cũng có lỗi riêng.

Đây là use case **chỉ đọc để báo giá**. Nó chưa thực hiện đặt giữ kho, nên không chứng minh an toàn đồng thời khi hai khách cùng mua. Việc trừ tồn kho thực tế cần transaction/atomic update hoặc reservation trong các kiểm thử tích hợp thích hợp.

### 4.1. File production: phân biệt lỗi theo ý nghĩa

Tạo file **`src/main/java/com/example/shop/stock/StockQuoteService.java`**:

```java
package com.example.shop.stock;

import java.util.Objects;

public final class StockQuoteService {

    public record Product(String sku, long unitPriceVnd,
                          int available, boolean active) {
    }

    public record Quote(String sku, int quantity, long totalVnd) {
    }

    // Port: adapter có trách nhiệm trả Product, hoặc ném NotFound/Unavailable.
    @FunctionalInterface
    public interface ProductCatalog {
        Product find(String sku);
    }

    public static final class InvalidInputException extends RuntimeException {
        public InvalidInputException(String message) {
            super(message);
        }
    }

    public static final class BusinessStateException extends RuntimeException {
        public BusinessStateException(String message) {
            super(message);
        }
    }

    public static final class ProductNotFoundException extends RuntimeException {
        public ProductNotFoundException(String message) {
            super(message);
        }
    }

    public static final class CatalogUnavailableException extends RuntimeException {
        public CatalogUnavailableException(String message) {
            super(message);
        }
    }

    private final ProductCatalog catalog;

    public StockQuoteService(ProductCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
    }

    public Quote quote(String sku, int quantity) {
        // Input được xác thực trước khi gọi hệ thống bên ngoài.
        if (sku == null || sku.isBlank()) {
            throw new InvalidInputException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new InvalidInputException("quantity must be positive");
        }

        // Port trả Product không null hoặc ném lỗi đã phân loại.
        Product product = catalog.find(sku);
        if (product == null) {
            throw new IllegalStateException("Catalog violated non-null contract");
        }

        // Dữ liệu âm do catalog trả về là lỗi hợp đồng, không phải lỗi input.
        if (product.available() < 0 || product.unitPriceVnd() < 0) {
            throw new IllegalStateException("Catalog returned invalid product");
        }

        // Chỉ kiểm tra trạng thái nghiệp vụ sau khi dữ liệu catalog hợp lệ.
        if (!product.active()) {
            throw new BusinessStateException("product is inactive");
        }
        if (product.available() < quantity) {
            throw new BusinessStateException("insufficient stock");
        }

        long total = Math.multiplyExact(product.unitPriceVnd(), quantity);
        return new Quote(product.sku(), quantity, total);
    }
}
```

**Tại sao cần hai kiểm tra tách biệt?** `sku` rỗng hoặc `quantity <= 0` sai ngay từ input, không cần kết nối catalog. `product.active()` và `product.available()` chỉ biết sau khi đọc dữ liệu trạng thái. Nếu `catalog.find` ném `CatalogUnavailableException`, service **không** bắt nó để tạo `InvalidInputException`; vì vậy nguyên nhân được giữ nguyên.

Ví dụ thiết lập rõ **hợp đồng của port**: adapter trả `Product` không null khi tìm được; ném `ProductNotFoundException` khi sản phẩm không tồn tại; ném `CatalogUnavailableException` khi dependency không khả dụng. Đây là **thiết kế ví dụ**, không phải exception mặc định do Spring/HTTP client tự ném. Một adapter thật phải bắt lỗi HTTP/DB/timeout đúng loại để chuyển sang hợp đồng này.

Có một chi tiết cần phân tích: dữ liệu `available < 0` là sai hợp đồng. Trong ứng dụng thực, hãy **xác thực dữ liệu catalog trước khi dùng làm rule trạng thái**, để trạng thái không hợp lệ không bị báo nhầm thành “insufficient stock”. Trong ví dụ, trường hợp đó trả business-state do điều kiện `available < quantity` được kiểm trước; để giữ ý nghĩa phân loại chính xác, **đặt kiểm tra dữ liệu âm trước các business-state check**. Phiên bản hoàn chỉnh đã thể hiện ý tưởng kiểm tra lỗi hợp đồng, nhưng thứ tự cần được xem xét khi mở rộng adapter và test cho dữ liệu sai cấu trúc.

### 4.2. File test: dùng fake để tách nguyên nhân

Tạo file **`src/test/java/com/example/shop/stock/StockQuoteServiceTest.java`**:

```java
package com.example.shop.stock;

import org.junit.jupiter.api.Test;

import com.example.shop.stock.StockQuoteService.BusinessStateException;
import com.example.shop.stock.StockQuoteService.CatalogUnavailableException;
import com.example.shop.stock.StockQuoteService.InvalidInputException;
import com.example.shop.stock.StockQuoteService.Product;
import com.example.shop.stock.StockQuoteService.ProductCatalog;
import com.example.shop.stock.StockQuoteService.ProductNotFoundException;
import com.example.shop.stock.StockQuoteService.Quote;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StockQuoteServiceTest {

    private static final class FakeCatalog implements ProductCatalog {
        Product product;
        RuntimeException failure;
        int calls;

        @Override
        public Product find(String sku) {
            calls++;
            if (failure != null) {
                throw failure;
            }
            return product;
        }
    }

    private final FakeCatalog catalog = new FakeCatalog();
    private final StockQuoteService service = new StockQuoteService(catalog);

    @Test
    void blankSkuIsInvalidInputWithoutCatalogCall() {
        assertThrows(InvalidInputException.class,
                () -> service.quote("  ", 2));
        assertEquals(0, catalog.calls);
    }

    @Test
    void zeroQuantityIsInvalidInputWithoutCatalogCall() {
        assertThrows(InvalidInputException.class,
                () -> service.quote("BOOK-1", 0));
        assertEquals(0, catalog.calls);
    }

    @Test
    void activeProductWithStockReturnsQuote() {
        catalog.product = new Product("BOOK-1", 200_000L, 5, true);

        Quote quote = service.quote("BOOK-1", 2);

        assertEquals(new Quote("BOOK-1", 2, 400_000L), quote);
        assertEquals(1, catalog.calls);
    }

    @Test
    void inactiveProductIsBusinessStateError() {
        catalog.product = new Product("BOOK-1", 200_000L, 5, false);

        assertThrows(BusinessStateException.class,
                () -> service.quote("BOOK-1", 1));
        assertEquals(1, catalog.calls);
    }

    @Test
    void insufficientStockIsBusinessStateError() {
        catalog.product = new Product("BOOK-1", 200_000L, 1, true);

        assertThrows(BusinessStateException.class,
                () -> service.quote("BOOK-1", 2));
        assertEquals(1, catalog.calls);
    }

    @Test
    void negativeStockIsInvalidCatalogDataBeforeBusinessChecks() {
        catalog.product = new Product("BOOK-1", 200_000L, -5, false);

        assertThrows(IllegalStateException.class,
                () -> service.quote("BOOK-1", 1));
        assertEquals(1, catalog.calls);
    }

    @Test
    void negativeUnitPriceIsInvalidCatalogDataBeforeBusinessChecks() {
        catalog.product = new Product("BOOK-1", -1L, 5, false);

        assertThrows(IllegalStateException.class,
                () -> service.quote("BOOK-1", 1));
        assertEquals(1, catalog.calls);
    }

    @Test
    void catalogTimeoutRemainsDependencyError() {
        CatalogUnavailableException timeout =
                new CatalogUnavailableException("catalog timeout");
        catalog.failure = timeout;

        CatalogUnavailableException thrown =
                assertThrows(CatalogUnavailableException.class,
                        () -> service.quote("BOOK-1", 2));

        assertSame(timeout, thrown);
        assertEquals(1, catalog.calls);
    }

    @Test
    void missingProductHasItsOwnError() {
        catalog.failure =
                new ProductNotFoundException("BOOK-1 not found");

        assertThrows(ProductNotFoundException.class,
                () -> service.quote("BOOK-1", 2));
        assertEquals(1, catalog.calls);
    }

    @Test
    void invalidInputIsDetectedEvenWhenCatalogWouldFail() {
        catalog.failure =
                new CatalogUnavailableException("catalog unavailable");

        assertThrows(InvalidInputException.class,
                () -> service.quote("", -1));
        assertEquals(0, catalog.calls);
    }
}
```

Hai file đầy đủ dùng **Java 17+**, JUnit Jupiter 5+ và không cần Spring context. `FakeCatalog` là một port fake theo đúng phương thức `find`; biến `calls` chứng minh rằng đầu vào sai không dẫn tới I/O. Kiểu exception cụ thể cho phép test phân biệt ba nguyên nhân và tình huống “không tìm thấy”.

Để chạy trong dự án Spring Boot đã có `spring-boot-starter-test` hoặc JUnit Jupiter tương ứng, tại thư mục module chứa wrapper và cấu hình test:

```bash
# Maven Wrapper: chạy riêng lớp này
./mvnw -Dtest=StockQuoteServiceTest test

# Hoặc Gradle Wrapper khi task test dùng JUnit Platform
./gradlew test --tests "com.example.shop.stock.StockQuoteServiceTest"
```

Trên Windows dùng `mvnw.cmd` hoặc `gradlew.bat`; chỉ chạy lệnh phù hợp với build của dự án. Kết quả kỳ vọng: **8 phương thức test, đều PASS**, không có stdout nghiệp vụ bắt buộc. Tên file, package và class được giữ nhất quán. Nếu Gradle chưa cấu hình JUnit Platform, cần bật `useJUnitPlatform()`; việc chỉ đặt file trong `src/test/java` không bảo đảm engine được cấu hình đúng.

**Giới hạn kiểm thử:** các test trên chứng minh quy tắc phân loại của **service trong điều kiện fake catalog**. Chúng chưa chứng minh adapter HTTP/DB thật chuyển đúng timeout/404/503 sang exception port, transaction thật hoạt động hay HTTP handler trả status như mong muốn. Những điều đó thuộc adapter/integration/web test tương ứng.

## 5. Viết assertion đúng: nguyên nhân, không chỉ exception

Để test có giá trị chẩn đoán, xác minh nhiều lớp của cùng một hành vi:

| Điều cần chứng minh | Assertion phù hợp | Tại sao? |
|---|---|---|
| Đầu vào sai trước dependency | `assertThrows(InvalidInputException.class, ...)` và `assertEquals(0, catalog.calls)` | Biết rõ loại lỗi và không tốn/có side effect I/O |
| Sản phẩm inactive hoặc thiếu tồn | `assertThrows(BusinessStateException.class, ...)` | Không gán nhầm thành lỗi mạng |
| Catalog timeout | `assertThrows(CatalogUnavailableException.class, ...)` | Caller có tín hiệu failure phụ thuộc để xử lý |
| Exception gốc không bị thay sai | `assertSame(timeout, thrown)` trong ví dụ | Chứng minh service không ngụy tạo input error từ timeout |
| Thành công | `assertEquals(new Quote(...), quote)` | Bảo vệ kết quả nghiệp vụ thay vì chỉ kiểm không có exception |
| Mỗi ca dùng dependency đúng số lần | `assertEquals(1, catalog.calls)` | Tránh gọi lặp bất ngờ khi không có thiết kế retry |

**Test tên “invalidInput...” mà chỉ dùng `assertNotNull(exception)` là chưa đủ.** Nên test cả thông điệp/rule khi chúng là một phần của contract đáng ổn định, nhưng không đóng đinh message nội bộ chỉ để test không fail khi đổi câu chữ. Type, error code có ý nghĩa và side effect mới là những dấu hiệu chính.

Với Mockito, có thể dùng `verifyNoInteractions(catalog)` khi input sai và `verify(catalog, times(1)).find("BOOK-1")` khi gọi thành công, nhưng đây là **cú pháp minh họa** đòi hỏi mock được thiết lập bằng Mockito. Fake tự viết ở ví dụ hoàn chỉnh giúp quy tắc rõ mà không thêm các annotation/mock lifecycle không cần thiết.

## 6. Thứ tự kiểm tra và ranh giới bất biến

Một luồng hợp lý cho nhiều use case là:

```text
1. Validate input không cần I/O
      │ nếu sai -> InvalidInput
      ▼
2. Truy vấn dependency theo hợp đồng port
      │ nếu timeout/không kết nối -> DependencyFailure
      │ nếu not found -> NotFound theo contract
      ▼
3. Kiểm tra dữ liệu trả về có đúng hợp đồng nội bộ
      │ nếu schema/giá trị bất khả thi -> Internal/ContractFailure
      ▼
4. Kiểm tra trạng thái/rule nghiệp vụ
      │ nếu không thỏa -> BusinessStateConflict
      ▼
5. Tính toán/thực thi hành động và trả kết quả
```

**Đừng biến sơ đồ thành luật cứng cho mọi hệ thống.** Có rule đầu vào phụ thuộc dữ liệu đã tra cứu, hoặc một thao tác cần lock/transaction để bảo đảm quyết định vẫn đúng tại thời điểm ghi. Phần quan trọng là mỗi điều kiện có **nguồn sự thật** và **loại kết quả** xác định; không biến failure của bước đọc trạng thái thành kết luận “không đủ điều kiện nghiệp vụ”.

Trong code ví dụ phần 4, nếu muốn phân loại chính xác tình huống catalog trả `available < 0`, cần đưa kiểm tra **dữ liệu hợp đồng âm** lên trước điều kiện `available < quantity`. Trong dự án thực tế, adapter/DTO validation thường bảo vệ invariant này ngay khi parse response. Test phải có case riêng cho dữ liệu vô lý, thay vì dùng chung `BusinessStateException` với trường hợp kho hợp lệ nhưng không đủ số lượng.

## 7. Mapping sang HTTP: đề xuất, không phải quy tắc tuyệt đối

Trong Spring Boot REST API, có thể ánh xạ các lỗi đã phân loại thành HTTP status và mã lỗi ổn định:

| Loại lỗi | HTTP thường cân nhắc | Ví dụ response message/code |
|---|---|---|
| Request thiếu/vi phạm validation | **400 Bad Request** hoặc **422 Unprocessable Content** theo contract | `INVALID_QUANTITY`, `INVALID_SKU` |
| Tài nguyên hợp lệ về ID nhưng không tìm thấy | **404 Not Found** trong API tài nguyên phù hợp | `PRODUCT_NOT_FOUND` |
| Trạng thái hiện tại không cho thực hiện | **409 Conflict** hoặc **422** tùy ngữ nghĩa | `PRODUCT_INACTIVE`, `INSUFFICIENT_STOCK` |
| Dependency tạm thời không khả dụng | **503 Service Unavailable**, đôi khi **502/504** theo vai trò gateway và contract | `CATALOG_UNAVAILABLE` |
| Bug nội bộ/vi phạm invariant bất ngờ | **500 Internal Server Error** nếu không có ánh xạ cụ thể hơn | `INTERNAL_ERROR` |

HTTP status và error code là **điều cần thiết kế nhất quán ở API boundary**. Không phải mọi business exception đều phải dùng 409; ví dụ API có thể quy định lỗi rule ở 422. Không có quy tắc “mọi exception của remote client trả về 503”; nếu remote trả lỗi nghiệp vụ có cấu trúc, adapter có thể diễn giải thành từ chối nghiệp vụ.

Khi áp dụng `@RestControllerAdvice`, hãy giữ error response ổn định: mã có thể xử lý bằng máy, thông báo an toàn cho người dùng, request/trace ID hỗ trợ debug. Không lộ credentials, URL nội bộ, stack trace hay chi tiết DB vào response. Unit test của service kiểm type/cause; một **web slice test** khác chứng minh HTTP mapping, response body và validation thực tế.

### Tại sao không bắt mọi lỗi rồi ném `InvalidInputException`?

Đây là **anti-pattern**:

```java
try {
    return catalog.find(sku);
} catch (Exception ex) {
    throw new InvalidInputException("Invalid SKU");
}
```

Đoạn minh họa này giả định đang ở lớp có `catalog`, `sku` và exception đã định nghĩa. Nếu catalog timeout, downstream 503, code NPE hoặc lỗi mapping, tất cả bị đổi thành “SKU sai”. Người dùng bị yêu cầu sửa dữ liệu vô ích và hệ thống không có tín hiệu sự cố thật. Nếu cần chuyển exception thư viện thành exception port, **bắt đúng nhóm lỗi transport** và giữ cause:

```java
try {
    return remoteClient.lookup(sku);
} catch (SocketTimeoutException ex) {
    throw new CatalogUnavailableException(
            "catalog request timed out", ex);
}
```

Đây cũng là **snippet adapter**, chưa phải file độc lập. Ví dụ đòi hỏi `CatalogUnavailableException` có constructor nhận `Throwable` và `remoteClient.lookup` thực sự có thể ném `SocketTimeoutException`; các HTTP client Spring khác nhau dùng loại exception timeout khác nhau. Khi áp dụng phải bắt đúng exception của client đang dùng, đồng thời bảo toàn cause để quan sát vận hành.

## 8. Retry, logging và side effect theo loại lỗi

- **Invalid input:** thường không retry nguyên dữ liệu. Ghi mã validation có cấu trúc, tránh log toàn bộ thông tin nhạy cảm.
- **Business-state conflict:** thường không tự retry ngay cùng một hành động; có thể chờ trạng thái đổi hoặc yêu cầu người dùng chỉnh lựa chọn. Nếu có retry do cạnh tranh transaction, cần quy tắc nhất quán và giới hạn rõ.
- **Dependency failure:** có thể retry **chỉ khi lỗi được xác định là tạm thời** và thao tác an toàn để thử lại. Có timeout, backoff, giới hạn lượt thử; theo dõi circuit breaker/metrics nếu phù hợp.
- **Bug/invariant failure:** cần điều tra nguồn dữ liệu hoặc code; retry vô hạn thường chỉ tăng tải và che nguyên nhân.

Đặc biệt với **ghi tiền, tạo đơn, phát sự kiện**, timeout không chứng minh thao tác chưa được thực hiện. Một request có thể đã được remote xử lý nhưng response mất. Nếu retry không có **idempotency key** hoặc cơ chế chống ghi trùng, có nguy cơ tạo side effect hai lần. Unit test service có thể kiểm chính sách quyết định retry; integration/contract test cần chứng minh hệ thống thực sự xử lý timeout, idempotency và giao dịch đúng ranh giới.

Trong log, nên phân biệt `INPUT_REJECTED`, `STATE_CONFLICT`, `DEPENDENCY_TIMEOUT` bằng metric hoặc structured field; giữ correlation ID để truy dấu. Không dùng log severity ERROR cho mọi input invalid, vì nó làm nhiễu cảnh báo vận hành.

## 9. Những nhầm lẫn phổ biến

1. **Thấy `IllegalArgumentException` là kết luận input HTTP sai.** Exception loại này có thể xuất phát từ bug, thư viện hoặc tham số nội bộ; nguồn ném và hợp đồng mới quyết định cách phân loại.
2. **Gặp HTTP 404 của upstream là chắc chắn input thiếu.** SKU có thể đúng cú pháp nhưng tài nguyên không tồn tại, bị ẩn hoặc hợp đồng remote khác; cần thiết kế not-found riêng.
3. **Gặp HTTP 409/422 của downstream là lỗi mạng.** Có thể là phản hồi nghiệp vụ hợp lệ; adapter phải hiểu schema/code trước khi kết luận.
4. **Mọi lỗi 5xx đều là “hết hàng” hoặc “không đủ điều kiện”.** Thiếu bằng chứng trạng thái; nên chuyển dependency failure với mã lỗi thích hợp.
5. **Dùng một exception chung cho toàn bộ lỗi.** Caller không thể biết sửa input, đổi trạng thái hay retry an toàn.
6. **Chỉ assert exception mà không assert số lần gọi dependency.** Input sai có thể vẫn gây request mạng hoặc ghi DB trước khi bị từ chối.
7. **Mock luôn dependency trả business value, không kiểm failure path.** Unit test xanh ở happy path nhưng không phát hiện bug ở adapter/service khi timeout hoặc invalid state.
8. **Nhầm trạng thái nghiệp vụ với dữ liệu sai hợp đồng.** `available = 0` là trạng thái kho hợp lệ; `available = -5` thường cho biết dữ liệu upstream bất thường.
9. **Dùng retry để “giải quyết” input sai hay giao dịch có side effect.** Retry không thay đổi dữ liệu sai và có thể gây duplicate khi timeout.
10. **Đưa mã HTTP vào model domain rồi test mọi thứ qua MockMvc.** Unit test nên kiểm rule bằng object trực tiếp; web slice/integration test riêng xác nhận ánh xạ HTTP.

## 10. Checklist trước khi hoàn thiện unit test nghiệp vụ

- [ ] Tôi xác định được **nguồn sự thật** của từng điều kiện: input, trạng thái entity hay dependency.
- [ ] Các điều kiện đầu vào có thể kiểm tra cục bộ được validate **trước khi gọi dependency**.
- [ ] Business-state violation không bị nhầm với lỗi request format hoặc timeout.
- [ ] Lỗi transport, DB/HTTP timeout được adapter phân loại có ý nghĩa, giữ cause khi chuyển exception.
- [ ] Resource not found và dữ liệu upstream vi phạm hợp đồng được xử lý theo chính sách rõ ràng.
- [ ] Unit test kiểm **kiểu exception cụ thể** và hành vi, không chỉ “ném RuntimeException”.
- [ ] Với input sai, test chứng minh **không có dependency call/side effect**; với lỗi phụ thuộc, test chứng minh không ngụy tạo kết quả nghiệp vụ.
- [ ] Với thành công, test kiểm đầu ra nghiệp vụ thực tế, trường hợp biên và số lần gọi quan trọng.
- [ ] HTTP status/error code được kiểm riêng ở tầng controller/advice theo contract.
- [ ] Retry chỉ áp dụng khi thích hợp; với side effect, có idempotency/transaction và integration test cần thiết.

**Nguyên tắc cốt lõi:** *Input sai* có thể xác định từ request; *trạng thái nghiệp vụ* chỉ kết luận được khi có dữ liệu trạng thái đáng tin; *dependency failure* nghĩa là chưa lấy được bằng chứng cần thiết. Unit test tốt phải giữ ba kết luận này tách biệt và chứng minh hệ thống không làm thêm hành động ngoài ý muốn khi từ chối yêu cầu.
