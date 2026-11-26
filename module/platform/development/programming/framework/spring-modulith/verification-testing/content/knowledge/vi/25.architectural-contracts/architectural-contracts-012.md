# Phân biệt contract test với implementation test

## 1. Cùng một chức năng, hai câu hỏi kiểm thử khác nhau

Giả sử application module `catalog` cung cấp báo giá cho module `orders`. Hiện tại `catalog` đọc giá từ một `Map` trong bộ nhớ. Sau refactor, nhóm phát triển chuyển sang database và thêm cache. Bài test cũ có assertion:

```java
verify(priceStore).findBySku("SKU-1");
```

Nó đỏ vì cache khiến lời gọi tới store không còn diễn ra ở lần truy vấn thứ hai. Nhưng module `orders` vẫn nhận đúng báo giá và đúng loại lỗi; không có hợp đồng công khai nào bị phá.

Trong trường hợp đó, test đang **bám vào cách implementation làm việc**, không trực tiếp chứng minh lời hứa mà `catalog` đưa ra cho consumer.

So sánh với assertion:

```java
assertThat(catalog.quote("SKU-1", 2))
    .isEqualTo(new PriceQuote(
        "SKU-1", 2, "VND", 120000L, 240000L));
```

Nếu đổi `Map` thành JPA mà kết quả vẫn đúng, assertion này vẫn xanh. Nếu tính sai tổng tiền, nó đỏ, bất kể dùng repository, cache hay thuật toán mới. Đó là đặc trưng của **contract test**.

Bài thuộc chương **Architectural contracts** trong học phần `SPRING_MODULITH_VERIFICATION_TESTING`. Mục tiêu là phân biệt rõ điều nào nên giữ cố định khi refactor, dùng `ApplicationModules.verify()` kiểm chứng ranh giới, `@ApplicationModuleTest` kiểm thử lời hứa giữa module, và đặt các phép kiểm có ý nghĩa vào quality gate CI.

**Định nghĩa thực hành:**

- **Contract test** kiểm tra hành vi hoặc cấu trúc mà **consumer được phép phụ thuộc**: API, input/output, lỗi, sự kiện, thứ tự/transaction nếu được cam kết, ranh giới module.
- **Implementation test** kiểm tra cách một implementation cụ thể đạt kết quả: lời gọi repository, cache, lựa chọn thuật toán, nhánh xử lý nội bộ, tương tác với dependency private.

Không phải implementation test “xấu”. Nó có ích để phát hiện lỗi thuật toán và tối ưu hóa. Rủi ro là **nhầm một chi tiết nội bộ thành public contract**, khiến refactor hợp lệ phải sửa hàng loạt test, hoặc tưởng rằng test mock đã chứng minh provider production đúng.

## 2. Nhận diện bằng câu hỏi: điều gì phải được giữ khi thay implementation?

| Tiêu chí | Contract test | Implementation test |
| --- | --- | --- |
| Người hưởng lợi | Caller/consumer, owner của API/sự kiện | Nhóm duy trì thuật toán hoặc adapter |
| Đối tượng quan sát | Kết quả công khai, lỗi, event, ranh giới | Private/internal collaborator, số lần gọi, cache, query |
| Khi thay Map bằng DB | Lý tưởng vẫn giữ nguyên | Có thể cần viết lại |
| Khi đổi giá 240000 thành 240 | **Phải đỏ** nếu đơn vị là một phần contract | Có thể không đỏ nếu chỉ `verify(findBySku)` |
| Khi đổi exception công khai | **Phải đỏ** | Có thể không kiểm tra |
| Khi thêm cache đúng semantics | Thường vẫn xanh | Có thể đỏ vì số lần gọi repo thay đổi |
| Chi phí bảo trì | Gắn với thay đổi hợp đồng | Gắn với thay đổi cấu trúc implementation |
| Điểm dễ sai | Test chỉ happy path, mock cả provider | Test quá nhiều interactions/số lần gọi |

**Phân loại không phụ thuộc annotation.** Một JUnit unit test thuần có thể là contract test nếu nó gọi API công khai và kiểm tra kết quả. Một `@SpringBootTest` hoặc `@ApplicationModuleTest` vẫn có thể là implementation test nếu nó chỉ assert `verify(repository).save(...)`. Mockito cũng không tự làm bài test thuộc loại nào; điều quan trọng là **đối tượng thật đang chạy và phần được assert**.

### Hai nghĩa của “contract test” cần phân biệt

Trong một modulith, thuật ngữ thường chỉ **module/API contract test**: provider và consumer cùng bảo vệ các lời hứa ở ranh giới module.

Trong hệ thống deploy độc lập, **consumer-driven contract test** còn có nghĩa cụ thể: consumer công bố kỳ vọng về giao tiếp HTTP/message; provider xác minh mình đáp ứng kỳ vọng đó. Bài này tập trung vào **contract nội bộ giữa application modules**, có nêu những điểm cần mở rộng khi giao tiếp qua Kafka hoặc HTTP, không tự nhận đã triển khai một công cụ consumer-driven contract như Pact.

## 3. Ví dụ xuyên suốt: contract công khai và implementation riêng của catalog

Ta dùng một ứng dụng Spring Boot có hai application modules `catalog` và `orders`. Theo convention nhận diện module mặc định phổ biến, package con trực tiếp của root application là một module.

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── catalog/
│   ├── CatalogQuotes.java
│   ├── PriceQuote.java
│   ├── UnknownSkuException.java
│   └── internal/
│       ├── PriceStore.java
│       ├── StaticPriceStore.java
│       └── CatalogPricingService.java
└── orders/
    ├── package-info.java
    ├── OrderQuoteService.java
    ├── OrderQuoteResult.java
    └── OrderQuoted.java

src/test/java/com/example/shop/
├── ModuleArchitectureTest.java
├── catalog/
│   └── CatalogProviderContractTest.java
├── catalog/internal/
│   └── CatalogPricingServiceInternalTest.java
└── orders/
    ├── OrdersConsumerContractTest.java
    └── OrdersCatalogIntegrationTest.java
```

### API công khai do `catalog` sở hữu

```java
// src/main/java/com/example/shop/catalog/CatalogQuotes.java
package com.example.shop.catalog;

public interface CatalogQuotes {
    PriceQuote quote(String sku, int quantity);
}
```

```java
// src/main/java/com/example/shop/catalog/PriceQuote.java
package com.example.shop.catalog;

public record PriceQuote(
    String sku,
    int quantity,
    String currency,
    long unitPriceMinor,
    long totalMinor
) {
}
```

```java
// src/main/java/com/example/shop/catalog/UnknownSkuException.java
package com.example.shop.catalog;

public class UnknownSkuException extends RuntimeException {
    public UnknownSkuException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

**Hợp đồng V1** được `orders` quyền sử dụng:

| Contract ID | Input | Kết quả công khai |
| --- | --- | --- |
| `CAT-01` | `quote("SKU-1", 2)`; mỗi đơn vị giá 120000 VND | `PriceQuote("SKU-1", 2, "VND", 120000, 240000)` |
| `CAT-02` | Quantity bằng 0 hoặc âm, hoặc SKU blank | `IllegalArgumentException` |
| `CAT-03` | SKU không tồn tại | `UnknownSkuException`, không trả `null` |
| `CAT-04` | Cùng dữ liệu giá và cùng input hợp lệ | Kết quả có cùng semantics, không phụ thuộc loại storage |
| `ARCH-01` | `orders` dùng `catalog` | Chỉ import API public, không import `catalog.internal` |

`CAT-04` không hứa *bao nhiêu lần đọc DB* hoặc *có cache hay không*. Nếu một latency SLA thực sự được cam kết, cần một **performance contract test** riêng với ngưỡng/phương pháp đo phù hợp, không mặc nhiên khóa mọi `verify(store)` thành API contract.

### Implementation nội bộ

```java
// src/main/java/com/example/shop/catalog/internal/PriceStore.java
package com.example.shop.catalog.internal;

import java.util.Optional;

interface PriceStore {
    Optional<UnitPrice> find(String sku);
}

record UnitPrice(String currency, long amountMinor) {
}
```

```java
// src/main/java/com/example/shop/catalog/internal/StaticPriceStore.java
package com.example.shop.catalog.internal;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
class StaticPriceStore implements PriceStore {

    private final Map<String, UnitPrice> prices = Map.of(
        "SKU-1", new UnitPrice("VND", 120000L),
        "SKU-2", new UnitPrice("VND", 99000L));

    @Override
    public Optional<UnitPrice> find(String sku) {
        return Optional.ofNullable(prices.get(sku));
    }
}
```

```java
// src/main/java/com/example/shop/catalog/internal/CatalogPricingService.java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.CatalogQuotes;
import com.example.shop.catalog.PriceQuote;
import com.example.shop.catalog.UnknownSkuException;
import org.springframework.stereotype.Service;

@Service
class CatalogPricingService implements CatalogQuotes {

    private final PriceStore store;

    CatalogPricingService(PriceStore store) {
        this.store = store;
    }

    @Override
    public PriceQuote quote(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException(
                "SKU and quantity must be valid");
        }

        UnitPrice price = store.find(sku)
            .orElseThrow(() -> new UnknownSkuException(sku));

        if (price.amountMinor() <= 0) {
            throw new IllegalStateException(
                "Invalid price configuration");
        }

        long total = Math.multiplyExact(
            price.amountMinor(), quantity);

        return new PriceQuote(
            sku, quantity, price.currency(),
            price.amountMinor(), total);
    }
}
```

`CatalogPricingService` chỉ là implementation. `PriceStore` và `UnitPrice` là các kiểu package-private thuộc `catalog.internal`; module `orders` không được dùng chúng.

Lớp ứng dụng gốc:

```java
// src/main/java/com/example/shop/ShopApplication.java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Code ví dụ chọn `Map` để không lẫn thêm database. Khi production dùng JPA, cần integration test cho SQL, transaction và migration, nhưng **các điều khoản `CAT-01/02/03` vẫn giữ nguyên**.

## 4. Provider contract test: chạy implementation thật qua public interface

Test đặt tại package `catalog` nên `@ApplicationModuleTest` bootstrap module provider. Không mock `CatalogQuotes` hoặc `CatalogPricingService`: nếu làm vậy, ta chỉ kiểm thử stub do chính test viết.

```java
// src/test/java/com/example/shop/catalog/CatalogProviderContractTest.java
package com.example.shop.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
class CatalogProviderContractTest {

    @Autowired
    CatalogQuotes catalog;  // Bean production thật.

    @Test
    void cat01_returnsPublicQuoteContract() {
        PriceQuote quote = catalog.quote("SKU-1", 2);

        assertThat(quote).isEqualTo(
            new PriceQuote(
                "SKU-1", 2, "VND",
                120000L, 240000L));
    }

    @Test
    void cat02_rejectsNonPositiveQuantity() {
        assertThatThrownBy(() ->
            catalog.quote("SKU-1", 0))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void cat03_rejectsUnknownSkuWithPublicError() {
        assertThatThrownBy(() ->
            catalog.quote("MISSING", 1))
            .isInstanceOf(UnknownSkuException.class);
    }

    @Test
    void cat04_sameRequestKeepsSameMeaning() {
        assertThat(catalog.quote("SKU-1", 2))
            .isEqualTo(catalog.quote("SKU-1", 2));
    }
}
```

**Vì sao đây là contract test?**

- Test gọi **interface công khai `CatalogQuotes`**, không gọi `PriceStore`.
- Assertion kiểm tra output và exception mà caller được phép phụ thuộc.
- Không phụ thuộc implementation đọc `Map`, JPA hay cache.
- Khi thay internal adapter nhưng giữ ngữ nghĩa, test có thể giữ nguyên.
- Khi provider đổi đơn vị tiền hoặc trả `null` cho SKU lạ, test phải đỏ.

**Điều không được suy từ test:** JPA commit, SQL constraint, Kafka delivery hoặc provider ngoài JVM đã hoạt động. `@ApplicationModuleTest` tạo context ở phạm vi module; test này chỉ có bean pricing và in-memory store. Nó kiểm chứng **hành vi provider trong điều kiện fixture được chọn**, không khẳng định mọi dữ liệu sản xuất đều hợp lệ.

### Cải tiến quan trọng: test data phải thể hiện hợp đồng

Một assertion như:

```java
assertThat(catalog.quote("SKU-1", 2))
    .isNotNull();
```

quá yếu: nó vẫn xanh nếu `totalMinor=240` thay vì `240000`. Một test hợp đồng phải khóa **giá trị và nghĩa dữ liệu mà consumer dựa vào**.

Với sự kiện hoặc DTO công khai, tiếp tục kiểm tra field, type, currency/units và negative paths, không chỉ một object tồn tại.

## 5. Implementation test: kiểm tra `PriceStore`, cache và cách phối hợp

Implementation test có thể chạy **không cần Spring context**, vì nó tập trung một class nội bộ và dependency private.

```java
// src/test/java/com/example/shop/catalog/internal/
// CatalogPricingServiceInternalTest.java
package com.example.shop.catalog.internal;

import com.example.shop.catalog.PriceQuote;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CatalogPricingServiceInternalTest {

    @Test
    void delegatesValidSkuToPriceStore() {
        PriceStore store = mock(PriceStore.class);

        when(store.find("SKU-1"))
            .thenReturn(Optional.of(
                new UnitPrice("VND", 120000L)));

        var service = new CatalogPricingService(store);

        PriceQuote quote = service.quote("SKU-1", 2);

        assertThat(quote.totalMinor()).isEqualTo(240000L);
        verify(store).find("SKU-1");
    }

    @Test
    void invalidInputNeverQueriesStore() {
        PriceStore store = mock(PriceStore.class);
        var service = new CatalogPricingService(store);

        org.assertj.core.api.Assertions
            .assertThatThrownBy(() ->
                service.quote("", 1))
            .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(store);
    }
}
```

**Nó có ích ở đâu?**

- Kiểm tra nhánh phối hợp cụ thể giữa service và store.
- Bắt lỗi vô tình truy vấn datastore khi input đã sai.
- Khi triển khai cache, xác minh chính sách hit/miss nếu performance là requirement.
- Khi viết adapter JPA, kiểm tra mapping query hoặc update bằng integration test riêng.

**Nó giòn ở đâu?** `verify(store).find("SKU-1")` giả định service luôn gọi trực tiếp store. Nếu refactor sang cache và trả quote đúng từ cache, test có thể đỏ **không vì contract công khai sai**, mà vì chi tiết nội bộ thay đổi. Khi đó review implementation test và điều chỉnh theo thiết kế mới; không sửa public contract để làm vừa assertion cũ.

### Một anti-pattern cần nhận diện

```java
@Test
void shouldQuote() {
    CatalogQuotes catalog = mock(CatalogQuotes.class);

    when(catalog.quote("SKU-1", 2))
        .thenReturn(new PriceQuote(
            "SKU-1", 2, "VND",
            120000L, 240000L));

    assertThat(catalog.quote("SKU-1", 2).totalMinor())
        .isEqualTo(240000L);
}
```

Đây **không phải provider contract test**: test chỉ khẳng định Mockito trả đúng dữ liệu nó vừa được bảo trả. Không có một dòng code provider production nào được thực thi. Mockito là công cụ tốt để **cô lập caller**, không phải bằng chứng thay thế implementation provider.

**Phân loại không cứng nhắc:** một implementation test cũng có thể kiểm tra outcome, và một provider contract test có thể dùng fake cho *adapter ngoài module* nếu nó vẫn chạy logic provider thật. Điều quyết định là **lời hứa nào được kiểm và lớp nào thực sự được chạy**.

## 6. Consumer contract test: caller dùng API như đã hứa

Để thấy chiều còn lại, module `orders` gọi public API `CatalogQuotes`:

```java
// src/main/java/com/example/shop/orders/OrderQuoteResult.java
package com.example.shop.orders;

public record OrderQuoteResult(
    String orderId,
    String currency,
    long totalMinor
) {
}
```

```java
// src/main/java/com/example/shop/orders/OrderQuoted.java
package com.example.shop.orders;

public record OrderQuoted(
    String orderId,
    String sku,
    int quantity,
    String currency,
    long totalMinor
) {
}
```

```java
// src/main/java/com/example/shop/orders/OrderQuoteService.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogQuotes;
import com.example.shop.catalog.PriceQuote;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderQuoteService {

    private final CatalogQuotes catalog;
    private final ApplicationEventPublisher events;

    public OrderQuoteService(
            CatalogQuotes catalog,
            ApplicationEventPublisher events) {
        this.catalog = catalog;
        this.events = events;
    }

    public OrderQuoteResult quoteForOrder(
            String orderId, String sku, int quantity) {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                "Order ID must not be blank");
        }

        PriceQuote quote = catalog.quote(sku, quantity);

        events.publishEvent(new OrderQuoted(
            orderId,
            quote.sku(),
            quote.quantity(),
            quote.currency(),
            quote.totalMinor()));

        return new OrderQuoteResult(
            orderId, quote.currency(), quote.totalMinor());
    }
}
```

Lưu ý `OrderQuoted` là một **domain event về việc đã lập báo giá**, không phải bằng chứng đơn hàng đã thanh toán/commit hoặc message đã gửi ra broker. Service ví dụ không có transaction hay repository.

### Test module `orders` với collaborator giả

```java
// src/test/java/com/example/shop/orders/OrdersConsumerContractTest.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogQuotes;
import com.example.shop.catalog.PriceQuote;
import com.example.shop.catalog.UnknownSkuException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ApplicationModuleTest
class OrdersConsumerContractTest {

    @Autowired
    OrderQuoteService orders; // Caller thật.

    @MockitoBean
    CatalogQuotes catalog; // API module ngoài.

    @Test
    void consumesKnownQuoteAndPublishesMatchingEvent(
            PublishedEvents events) {

        given(catalog.quote("SKU-1", 2))
            .willReturn(new PriceQuote(
                "SKU-1", 2, "VND",
                120000L, 240000L));

        OrderQuoteResult result =
            orders.quoteForOrder("ORD-1", "SKU-1", 2);

        assertThat(result).isEqualTo(
            new OrderQuoteResult(
                "ORD-1", "VND", 240000L));

        verify(catalog).quote("SKU-1", 2);

        assertThat(events.ofType(OrderQuoted.class))
            .singleElement()
            .satisfies(event -> {
                assertThat(event.orderId())
                    .isEqualTo("ORD-1");
                assertThat(event.sku()).isEqualTo("SKU-1");
                assertThat(event.quantity()).isEqualTo(2);
                assertThat(event.currency()).isEqualTo("VND");
                assertThat(event.totalMinor())
                    .isEqualTo(240000L);
            });
    }

    @Test
    void noSuccessEventWhenProviderRejectsSku(
            PublishedEvents events) {

        given(catalog.quote("MISSING", 1))
            .willThrow(new UnknownSkuException("MISSING"));

        assertThatThrownBy(() ->
            orders.quoteForOrder("ORD-2", "MISSING", 1))
            .isInstanceOf(UnknownSkuException.class);

        assertThat(events.ofType(OrderQuoted.class))
            .isEmpty();
    }
}
```

`@MockitoBean` được cung cấp từ Spring Framework 6.2+ trên stack Boot/Modulith tương thích; nếu dự án dùng stack cũ, cần annotation thay thế tương thích như `@MockBean`.

### Tại sao test này được gọi là consumer contract test?

- **`OrderQuoteService` thật được chạy**, không mock caller.
- `CatalogQuotes` ở module khác được mô phỏng theo những kết quả/lỗi mà provider đã hứa.
- Test kiểm tra caller dùng đúng `currency`/`totalMinor` và không phát `OrderQuoted` nếu nhận lỗi.
- `PublishedEvents` kiểm tra **event được công bố trong Spring context**, không chứng minh event đã externalized.

**Giới hạn then chốt:** test vẫn có thể xanh nếu provider production đã đổi `UnknownSkuException` thành `null`—vì Mockito tiếp tục ném exception theo giả định của caller. Bởi vậy phải có **provider contract test** độc lập; nếu rủi ro đủ lớn, thêm integration test chạy cả hai module thật.

## 7. Cross-module integration test: kiểm tra hai phía có còn đồng ý không

Đặt ranh giới module trong `orders/package-info.java`:

```java
// src/main/java/com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.example.shop.orders;
```

Trong `@ApplicationModuleTest` của `orders`, chọn mode nạp các dependency trực tiếp:

```java
// src/test/java/com/example/shop/orders/OrdersCatalogIntegrationTest.java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest(
    mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersCatalogIntegrationTest {

    @Autowired
    OrderQuoteService orders;

    @Test
    void realCallerWorksWithRealProvider(
            PublishedEvents events) {

        OrderQuoteResult result =
            orders.quoteForOrder("ORD-IT-1", "SKU-1", 2);

        assertThat(result).isEqualTo(
            new OrderQuoteResult(
                "ORD-IT-1", "VND", 240000L));

        assertThat(events.ofType(OrderQuoted.class))
            .singleElement()
            .satisfies(event ->
                assertThat(event.totalMinor())
                    .isEqualTo(240000L));
    }
}
```

Trong ví dụ, `orders` import `CatalogQuotes`, tạo một dependency trực tiếp tới `catalog` theo mô hình module; mode `DIRECT_DEPENDENCIES` nạp provider thật và `StaticPriceStore` thật, không sử dụng `@MockitoBean CatalogQuotes`.

**Ba tầng bằng chứng không thay thế nhau:**

| Bài kiểm | Caller thật | Provider thật | Đích xác minh |
| --- | --- | --- | --- |
| Provider contract | Không | Có | `catalog` giữ hành vi API V1 |
| Consumer contract | Có | Không (mock API) | `orders` dùng đúng lời hứa |
| Cross-module integration | Có | Có | Wiring và kết quả thực giữa hai module |

Không cần một giant `@SpringBootTest` chỉ để xác minh báo giá. Nhưng nếu integration thực có DataSource/JPA/HTTP hay messaging, cần test infrastructure tương ứng; `DIRECT_DEPENDENCIES` **không tự tạo** broker hoặc database.

### Mở rộng negative integration

Khi thay provider implementation, nên bổ sung case gọi `MISSING` với provider thật và assert `OrderQuoted` rỗng. Khi đó nếu provider vô tình trả `null` hoặc thay exception, bài test tích hợp sẽ phát hiện ở boundary thật, không chỉ trong stub.

## 8. Architectural contract khác mọi test hành vi bên trên

Provider và consumer có thể trả đúng dữ liệu dù caller vô tình import `catalog.internal` ở một class khác. Để chặn điều đó, chạy kiểm chứng cấu trúc độc lập:

```java
// src/test/java/com/example/shop/ModuleArchitectureTest.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesDeclaredModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ApplicationModules.verify()` kiểm tra những ràng buộc kiến trúc mà mô hình Spring Modulith hỗ trợ: dependency giữa modules, access tới API/internal và cycle/allowed dependencies theo cấu hình. Đây là **architectural contract test**: nó bảo vệ lời hứa về cấu trúc, không inspect runtime flow.

Một module `orders` **không được** phụ thuộc vào `catalog.internal.PriceStore`. Trong ví dụ này các type internal được khai báo package-private, nên Java compiler đã chặn một số truy cập. Nếu ai đó đổi visibility thành `public`, điều đó vẫn không tự biến chúng thành API module; architecture verification là lớp phòng vệ tiếp theo.

**Không gán quá nhiều năng lực cho một gate:**

- `ApplicationModules.verify()` **không** kiểm tra `quote("SKU-1", 2)` trả 240000.
- `@ApplicationModuleTest` **không tự** chặn mọi dependency sai chỉ vì context khởi động.
- `PublishedEvents` **không** xác nhận database commit hoặc Kafka broker ack.
- Mockito `verify(store).find(...)` **không** chứng minh consumer còn dùng API đúng.
- Testcontainers JPA **không** thay thế schema/version compatibility của event externalized.

Cùng một thay đổi có thể đòi **nhiều hợp đồng khác nhau**, mỗi hợp đồng có một loại bằng chứng phù hợp.

## 9. Refactor thử nghiệm: test nào nên giữ, test nào được đổi?

Giả sử nhóm `catalog` chuyển từ `StaticPriceStore` sang `JdbcPriceStore` có cache. Public API `CatalogQuotes` và ngữ nghĩa `PriceQuote` không đổi.

### Kỳ vọng sau refactor

| Test | Kỳ vọng | Lý do |
| --- | --- | --- |
| `CatalogProviderContractTest` | **Giữ nguyên** assertion, xanh khi giá đúng | Bảo vệ contract công khai |
| `OrdersConsumerContractTest` | **Giữ nguyên** | Caller vẫn dùng interface cũ |
| `OrdersCatalogIntegrationTest` | Giữ hành vi, thêm DB fixture nếu cần | Kết quả thực giữa hai module |
| `CatalogPricingServiceInternalTest` | **Có thể cần đổi** | `verify(store)` gắn với internal orchestration/cache |
| `ModuleArchitectureTest` | Giữ nguyên | Ranh giới `orders → catalog` vẫn như cũ |
| JDBC/repository integration mới | Bổ sung | Chỉ tầng này chứng minh SQL/mapping/commit |

**Thử phá từng hợp đồng để đánh giá sức mạnh test:**

| Mutation có chủ đích | Test phải đỏ |
| --- | --- |
| Đổi `unitPriceMinor` 120000 thành 120 | Provider contract và integration |
| Đổi unknown SKU từ exception thành `null` | Provider contract; negative integration nếu có |
| `orders` vẫn trả đúng receipt nhưng phát hai `OrderQuoted` | Consumer `singleElement()` |
| `orders` import một public class nằm trong `catalog.internal` | Architecture verification |
| Giữ quote đúng nhưng chuyển từ store sang cache | Contract có thể xanh; internal interaction test có thể cần cập nhật |
| JDBC query đọc sai cột hoặc bỏ unique constraint | JDBC/DB integration nếu được thêm |

### Khi nào implementation test đáng giữ?

Giữ nó khi có rủi ro **nội bộ thực sự cần được quan sát**: cache invalidation, concurrency, transaction isolation, batching, số truy vấn đã được định nghĩa như performance budget, hoặc recovery algorithm. Khi đó hãy ghi rõ **đó là invariant của implementation hiện tại**, và test có thể thay đổi khi giải pháp nội bộ thay đổi mà không tạo breaking public API.

Đừng sửa provider contract test theo một output mới chỉ để cho pipeline xanh nếu consumer vẫn phụ thuộc giá trị cũ. Ngược lại, đừng buộc team giữ một repository call chỉ vì một `verify(...)` mà không còn ý nghĩa sau refactor.

### Đừng nhầm mức độ cô lập với mục tiêu test

Một số hiểu nhầm thường gặp:

- “Unit test luôn là implementation test.” — Sai: unit test gọi API và kiểm tra contract cũng được.
- “Integration test luôn là contract test.” — Sai: integration test có thể chỉ assert số lần gọi internal bean.
- “Có `@ApplicationModuleTest` thì đương nhiên là contract test.” — Sai: annotation chỉ quy định cách bootstrap context.
- “Không mock thì mới là contract test.” — Không hẳn: consumer contract test dùng mock provider để kiểm tra **caller assumptions**; provider contract cần chạy implementation provider thật hoặc một adapter đủ phù hợp.
- “Contract test luôn chống mọi loại breaking change.” — Sai: Java method/exception, wire JSON, config, DB và side-effect delivery là những contract khác nhau cần test khác nhau.

## 10. Checklist chọn test và quality gate CI

Khi nhận một yêu cầu mới, có thể quyết định theo ba câu hỏi:

1. **Lời hứa này hướng ra ngoài implementation không?** Nếu có, viết test trên public result/error/event hoặc ranh giới kiến trúc.
2. **Assertion có phải quan sát cách làm nội bộ không?** Nếu có, xác định nó bảo vệ rủi ro gì và có nên thay khi refactor.
3. **Có hệ thống khác tham gia không?** Nếu có, chỉ thêm database/broker/HTTP integration khi nó là một phần của hợp đồng thực.

### Ma trận CI đề xuất

| Gate | Test | Loại bằng chứng |
| --- | --- | --- |
| Compile/Java source API | Compile toàn module phụ thuộc | Signature còn dùng được |
| Module architecture | `ModuleArchitectureTest` | Public/internal boundary, allowed dependencies |
| Provider behavior | `CatalogProviderContractTest` | Quote/error contract |
| Consumer behavior/event | `OrdersConsumerContractTest` | Assumptions và `OrderQuoted` |
| Small cross-module integration | `OrdersCatalogIntegrationTest` | Hai bên thật tương thích |
| Internal unit | `CatalogPricingServiceInternalTest` | Cách phối hợp với store, chỉ giữ khi có giá trị |
| DB integration (nếu thêm JDBC/JPA) | Testcontainers + migration/transaction assertions | SQL, constraint, commit/rollback |
| External messaging (nếu thêm) | Producer/consumer schema + broker integration | Payload, route, ack, replay/idempotency |

Với Gradle/JUnit 5, một workflow có thể chạy test suite bằng:

```bash
./gradlew test
```

Dự án cần cấu hình JUnit Platform, dependencies Spring Boot Test/Spring Modulith Test và version tương thích. Đây là lệnh minh họa cho CI; **không có Gradle/Python nào được chạy trong bước soạn bài**.

### Checklist review nhanh

- [ ] Public API có positive/negative tests kiểm tra giá trị và exception cụ thể.
- [ ] Provider contract test thực sự chạy implementation provider.
- [ ] Consumer test kiểm tra caller thật; mock chỉ thay API ngoài module khi cần.
- [ ] Nếu event là một phần contract, kiểm tra **payload và số lượng**, không chỉ `isNotEmpty()`.
- [ ] Có selected integration test với provider/caller thật cho rủi ro quan trọng.
- [ ] `ApplicationModules.verify()` là required CI gate độc lập.
- [ ] Internal interaction tests có lý do rõ, không biến optimization thành API contract.
- [ ] Thay storage không buộc đổi public contract assertions nếu behavior không đổi.
- [ ] Khi có database, kiểm tra SQL/commit bằng DB thật; khi có broker, kiểm tra transport và consumer thật ở mức phù hợp.
- [ ] Khi một contract được sửa có chủ đích, cập nhật owner/consumer, test và migration plan cùng lúc.

### Bài tập tự kiểm tra

**A.** Developer thêm cache. `catalog.quote(...)` vẫn trả đúng giá nhưng `verify(store).find("SKU-1")` không còn đúng ở lần hai. Bạn sửa test nào?  
**Đáp:** implementation test liên quan cách truy cập store/cache, nếu cache behavior được phê duyệt; không nới lỏng `CAT-01`.

**B.** Developer đổi `UnknownSkuException` thành `null`. Consumer module test dùng Mockito vẫn xanh. Test nào phải phát hiện?  
**Đáp:** `CatalogProviderContractTest`; thêm negative cross-module integration nếu đây là rủi ro cần bảo vệ xuyên module.

**C.** Developer đổi tên `PriceQuote.totalMinor` nhưng service nhận logic vẫn compile sau migration. Có thể coi là tương thích không?  
**Đáp:** chưa chắc. Đây là thay đổi public API/contract; kiểm tra consumer source/binary compatibility và semantics, cùng event wire nếu DTO đã được serialize ra ngoài.

**D.** Developer thêm `@SpringBootTest` rồi chỉ assert context loads. Đã có contract test chưa?  
**Đáp:** chưa có bằng chứng cụ thể. Phải xác định lời hứa nào và assertion nào sẽ fail khi lời hứa bị phá.

**Ghi nhớ:** **contract test bảo vệ *điều module hứa*; implementation test bảo vệ *cách module hiện thực lời hứa*.** Trong Spring Modulith, hãy dùng `ApplicationModules.verify()` cho ranh giới code, `@ApplicationModuleTest` cho hành vi provider/consumer, `PublishedEvents` cho domain publication và selected integration cho hợp tác thật. Khi kiểm thử đúng mục tiêu, refactor nội bộ có thể diễn ra tự do hơn mà CI vẫn bắt được những thay đổi làm hỏng consumer.
