# Contract test cho public API của module

> **Chương:** Test types  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Mục tiêu:** Xây dựng các phép kiểm tra hợp đồng cho public API của application module Spring Modulith, kết hợp kiểm chứng package/dependency bằng `ApplicationModules.verify()` với kiểm thử hành vi bằng `@ApplicationModuleTest` và quality gate CI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **public API của application module** với Java `public`, REST API và implementation nội bộ.
2. Liệt kê những điều tạo thành hợp đồng giữa module cung cấp (*provider*) và module sử dụng (*consumer*): chữ ký, kiểu dữ liệu, điều kiện đầu vào, kết quả, ngoại lệ, tính nhất quán và sự kiện.
3. Thiết kế một provider contract test sử dụng implementation thật trong `@ApplicationModuleTest`.
4. Thiết kế một consumer-facing integration test kiểm tra module gọi qua API công khai được hỗ trợ.
5. Dùng `ApplicationModules.verify()`, `@ApplicationModule(allowedDependencies = ...)` và `@NamedInterface` để bảo vệ ranh giới package.
6. Kiểm tra nguy cơ phá vỡ hợp đồng khi đổi tên, tham số, giá trị trả về, DTO/record hay schema sự kiện.
7. Tích hợp những phép kiểm tra này vào CI nhằm phát hiện hồi quy sớm mà vẫn giữ module có trách nhiệm rõ ràng.

Trong Spring Modulith, nhiều application module nằm chung một Spring Boot application và có thể gọi Java interface hoặc truyền sự kiện trực tiếp qua Spring. **Contract test cho public API của module** tập trung xác nhận rằng *những gì module công bố* vẫn có ý nghĩa và hành vi đúng đối với bên sử dụng. Mã biên dịch thành công là điều kiện cần, chưa đủ để chứng minh hợp đồng hành vi.

## 2. Hợp đồng module có những lớp nào?

Giả sử module `pricing` cung cấp giá hàng cho module `ordering`:

~~~mermaid
flowchart LR
    C["ordering<br/>consumer"] -->|"PriceCatalog.quote(...)"| A["pricing API<br/>PriceCatalog / PriceQuote"]
    A --> P["pricing.internal<br/>DefaultPriceCatalog"]
    T1["Provider contract test"] --> A
    T2["Consumer integration test"] --> C
    T3["ApplicationModules.verify()"] -.-> C
    T3 -.-> A
~~~

Bên sử dụng chỉ cần biết API của `pricing`. Bên cung cấp có thể thay đổi thuật toán, cấu trúc repository hoặc adapter mà không buộc `ordering` biết đến những chi tiết đó.

| Thành phần hợp đồng | Cần thống nhất | Ví dụ |
| --- | --- | --- |
| **Hình dạng API** | Tên class/interface, method, visibility, tham số và kiểu trả về | `PriceCatalog.quote(String, int)` |
| **Ngữ nghĩa đầu vào** | Giá trị hợp lệ, điều kiện biên, null và validation | Số lượng phải lớn hơn 0 |
| **Ngữ nghĩa kết quả** | Ý nghĩa từng trường, đơn vị, giá trị rỗng và bất biến | `Optional.empty()` khi SKU không tồn tại |
| **Lỗi** | Exception nào có thể phát sinh, khi nào và có rollback hay không | `IllegalArgumentException` với số lượng không hợp lệ |
| **Dữ liệu và transaction** | Dữ liệu trả về phản ánh thời điểm nào, có thể nhất quán sau một khoảng trễ không | Giá được tính trong lời gọi đồng bộ |
| **Sự kiện** | Tên/kiểu, payload, thời điểm phát, tính lặp và tương thích schema | `OrderPlaced` chứa ID và phiên bản hợp đồng |
| **Ranh giới kiến trúc** | Module nào được phép import API nào | `ordering → pricing` được phép; `ordering → pricing.internal` bị cấm |

**Ba lớp xác minh khác nhau** cần được kết hợp:

- *Biên dịch/kiểm tra kiểu* phát hiện class hoặc method không còn tồn tại, không tương thích tham số.
- *Architectural test* phát hiện module sử dụng class ngoài public API hoặc dependency trái quy tắc.
- *Behavioral contract test* kiểm tra kết quả và ngoại lệ theo những tình huống hợp đồng đã xác định.

Một test `ApplicationModules.verify()` xanh không chứng minh `quote(...)` trả đúng tổng tiền. Một provider test xanh cũng không tự chứng minh module consumer không import package nội bộ.

## 3. Public API của Spring Modulith là gì?

Giả sử ứng dụng Java 17+ có cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── pricing/
│   ├── PriceCatalog.java               # API công khai
│   ├── PriceQuote.java                 # DTO công khai
│   └── internal/
│       ├── DefaultPriceCatalog.java    # implementation
│       └── persistence/                # có thể thêm JPA adapter
└── ordering/
    ├── package-info.java               # giới hạn allowedDependencies
    ├── OrderTotals.java                # API của ordering
    └── internal/
        └── DefaultOrderTotals.java
~~~

Theo chiến lược phát hiện mặc định, `pricing` và `ordering` là application module nằm trực tiếp dưới package ứng dụng `com.example.shop`. Kiểu ở **root package của từng module** thuộc public API mặc định; kiểu ở các package con như `pricing.internal` thuộc phạm vi implementation, trừ khi được công bố bằng named interface.

### Phạm vi Java so với phạm vi module

~~~java
// Java public, nhưng nằm trong package implementation nội bộ:
package com.example.shop.pricing.internal;

public class PricingJpaAdapter {
    // ...
}
~~~

Module `ordering` vẫn có thể biên dịch khi import `PricingJpaAdapter` nếu class `public` và nằm trên classpath. Tuy nhiên, theo mô hình ranh giới mặc định của Spring Modulith, đó là tham chiếu **không hợp lệ** nếu package `internal` không được công bố.

Một import được phép trong ví dụ là:

~~~java
import com.example.shop.pricing.PriceCatalog;
import com.example.shop.pricing.PriceQuote;
~~~

Bài kiểm tra `ApplicationModules.verify()` ở mục 8 sẽ giúp phát hiện truy cập sai. Do vậy, **từ “public” trong tiêu đề bài chỉ API của application module**, không chỉ modifier `public` của Java.

### Không đồng nhất public module API với HTTP API

| API | Bên gọi | Cách gọi | Cách kiểm thử phù hợp |
| --- | --- | --- | --- |
| Public API của Modulith | Module Java khác trong cùng ứng dụng | Gọi interface/DTO hoặc subscribe typed event | Module/provider/consumer contract test và `verify()` |
| REST API | HTTP client | JSON, status, headers và URL | `@WebMvcTest`, REST contract test hoặc E2E |
| External message contract | Consumer qua broker | Event schema/serialization, topic, key | Contract/schema và integration test với broker |
| JPA entity/repository nội bộ | Implementation của chính module | SQL/JPA | `@DataJpaTest` và module/integration test |

Một API có thể được công bố ra REST nhưng DTO REST chưa chắc là public API cho các module Java; ngược lại, Java public API của module không nhất thiết có endpoint HTTP.

## 4. Xây dựng API mẫu: pricing cung cấp báo giá

Ta chọn quy tắc nghiệp vụ minh họa:

1. `pricing` quản lý bảng giá: `BOOK-01` có đơn giá 120,00 và `PEN-02` có đơn giá 10,00 (đơn vị tiền giả định đồng nhất trong ứng dụng ví dụ).
2. `quote(sku, quantity)` trả `Optional<PriceQuote>`. SKU không tồn tại thì trả `Optional.empty()`.
3. `sku` phải khác null/chuỗi trắng; `quantity` phải dương; đầu vào sai ném `IllegalArgumentException`.
4. `total = unitPrice × quantity`, dùng `BigDecimal` để giữ độ chính xác số thập phân.
5. `pricing` trả kiểu dữ liệu API bất biến, không đưa JPA entity hay class `internal` cho module khác.

Giá cố định trong ví dụ chỉ là **fixture minh họa hợp đồng**, không phải lời khuyên lưu giá production bằng hằng số. Khi triển khai thật, bảng giá thường thuộc database hoặc một nguồn cấu hình có kiểm soát; hợp đồng API và test provider có thể giữ nguyên dù adapter bên trong thay đổi.

### 4.1. Entry point ứng dụng

**`src/main/java/com/example/shop/ShopApplication.java`**

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

### 4.2. Interface công khai

**`src/main/java/com/example/shop/pricing/PriceCatalog.java`**

~~~java
package com.example.shop.pricing;

import java.util.Optional;

public interface PriceCatalog {

    /**
     * Returns a quote for a known SKU.
     * Empty means the SKU is not known.
     *
     * @throws IllegalArgumentException if sku is blank
     *         or quantity is not positive
     */
    Optional<PriceQuote> quote(String sku, int quantity);
}
~~~

**`src/main/java/com/example/shop/pricing/PriceQuote.java`**

~~~java
package com.example.shop.pricing;

import java.math.BigDecimal;

public record PriceQuote(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal total
) {}
~~~

Chọn `Optional` để thể hiện “không tìm thấy” ngay trong chữ ký và `record` để mang kết quả bất biến ở cấp cấu trúc. Đây là một phần **hợp đồng mà consumer phải hiểu đúng**. Đổi sang trả `null` hoặc phát ngoại lệ cho SKU không tồn tại sẽ là thay đổi ngữ nghĩa ngay cả khi compiler không phát hiện ở một số cách sử dụng.

Trong hệ thống có tiền tệ đa quốc gia, nên bổ sung currency vào hợp đồng và quy định làm tròn/precision; ví dụ này giả định các giá trị cùng một đơn vị để tập trung vào kỹ thuật kiểm thử.

### 4.3. Implementation nội bộ

**`src/main/java/com/example/shop/pricing/internal/DefaultPriceCatalog.java`**

~~~java
package com.example.shop.pricing.internal;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.example.shop.pricing.PriceCatalog;
import com.example.shop.pricing.PriceQuote;

@Service
class DefaultPriceCatalog implements PriceCatalog {

    private static final Map<String, BigDecimal> PRICES = Map.of(
            "BOOK-01", new BigDecimal("120.00"),
            "PEN-02", new BigDecimal("10.00"));

    @Override
    public Optional<PriceQuote> quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        return Optional.ofNullable(PRICES.get(sku))
                .map(unitPrice -> new PriceQuote(
                        sku,
                        quantity,
                        unitPrice,
                        unitPrice.multiply(
                                BigDecimal.valueOf(quantity))));
    }
}
~~~

Consumer không được tạo `new DefaultPriceCatalog()` hoặc tham chiếu class này; nó nhận `PriceCatalog` như dependency. Điều đó cho phép provider thay đổi implementation mà không phá import của consumer.

## 5. Provider contract test: kiểm tra API được cung cấp

Đặt bài test trong package module `pricing`, để Spring Modulith nhận diện đúng module của test.

**`src/test/java/com/example/shop/pricing/PriceCatalogContractTest.java`**

~~~java
package com.example.shop.pricing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class PriceCatalogContractTest {

    @Autowired
    PriceCatalog catalog;

    @Test
    void returns_a_quote_with_expected_fields_and_total() {
        var result = catalog.quote("BOOK-01", 2);

        assertThat(result).contains(new PriceQuote(
                "BOOK-01",
                2,
                new BigDecimal("120.00"),
                new BigDecimal("240.00")));
    }

    @Test
    void returns_empty_for_an_unknown_sku() {
        assertThat(catalog.quote("UNKNOWN", 1)).isEmpty();
    }

    @Test
    void rejects_a_non_positive_quantity() {
        assertThatThrownBy(() ->
                catalog.quote("BOOK-01", 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("quantity");
    }

    @Test
    void rejects_blank_sku() {
        assertThatThrownBy(() ->
                catalog.quote("   ", 1))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("sku");
    }
}
~~~

### Bằng chứng mà test cung cấp

- **Spring wiring:** Bean thực hiện `PriceCatalog` có trong context module; test inject theo interface, không phụ thuộc implementation.
- **Contract kết quả:** SKU, số lượng, đơn giá và tổng tiền khớp điều kiện đã công bố.
- **Contract “không tìm thấy”:** SKU lạ trả `Optional.empty()`.
- **Contract lỗi:** Input không hợp lệ bị từ chối bằng ngoại lệ có ý nghĩa.

Không mock `PriceCatalog` trong **provider contract test**. Nếu ta cấu hình mock trả đúng kết quả rồi assert lại kết quả ấy, test chỉ xác nhận hành vi mock, không chứng minh provider thực đáp ứng hợp đồng.

### Những điều test này chưa xác minh

| Phần chưa được chứng minh | Cách bổ sung |
| --- | --- |
| Consumer `ordering` gọi API đúng cách | Consumer/module integration test ở mục 6 |
| Module có import package `internal` trái phép | `ApplicationModules.verify()` ở mục 8 |
| Dữ liệu giá đọc đúng từ database production | JPA/integration test với database phù hợp |
| Thay đổi Java API tương thích với client đã build từ phiên bản cũ | Kiểm tra tương thích nguồn/binary theo chính sách phát hành |
| Event có được consumer xử lý sau commit hay không | Integration/event test nhiều module |

**Lưu ý về `BigDecimal`:** `record` sử dụng `equals` của các field. `BigDecimal.equals` có xét `scale`, nên `120.00` và `120.0` là hai đối tượng không `equals`. Trong ví dụ, `scale = 2` là một phần của fixture mong đợi. Nếu hợp đồng chỉ quy định giá trị số, test có thể dùng `compareTo(...) == 0` cho các khoản tiền, đồng thời kiểm tra riêng quy tắc làm tròn/định dạng được yêu cầu.

## 6. Consumer-facing test: kiểm tra module sử dụng API

Module `ordering` sử dụng `PriceCatalog`, **không** import `DefaultPriceCatalog`. Ta định nghĩa một API của `ordering` để tính tổng:

**`src/main/java/com/example/shop/ordering/OrderTotals.java`**

~~~java
package com.example.shop.ordering;

import java.math.BigDecimal;
import java.util.Optional;

public interface OrderTotals {

    Optional<BigDecimal> totalFor(String sku, int quantity);
}
~~~

**`src/main/java/com/example/shop/ordering/internal/DefaultOrderTotals.java`**

~~~java
package com.example.shop.ordering.internal;

import java.math.BigDecimal;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.example.shop.ordering.OrderTotals;
import com.example.shop.pricing.PriceCatalog;
import com.example.shop.pricing.PriceQuote;

@Service
class DefaultOrderTotals implements OrderTotals {

    private final PriceCatalog catalog;

    DefaultOrderTotals(PriceCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public Optional<BigDecimal> totalFor(
            String sku, int quantity) {

        return catalog.quote(sku, quantity)
                .map(PriceQuote::total);
    }
}
~~~

Để giới hạn chiều phụ thuộc được phép trong kiến trúc, module `ordering` có thể khai báo:

**`src/main/java/com/example/shop/ordering/package-info.java`**

~~~java
@ApplicationModule(allowedDependencies = "pricing")
package com.example.shop.ordering;

import org.springframework.modulith.ApplicationModule;
~~~

### 6.1. Kiểm thử consumer với implementation provider thật

Đặt test trong package `ordering`:

**`src/test/java/com/example/shop/ordering/OrderTotalsContractIntegrationTest.java`**

~~~java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(
        mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrderTotalsContractIntegrationTest {

    @Autowired
    OrderTotals totals;

    @Test
    void ordering_consumes_pricing_public_api() {
        assertThat(totals.totalFor("BOOK-01", 2))
                .contains(new BigDecimal("240.00"));
    }

    @Test
    void unknown_product_stays_unknown_to_consumer() {
        assertThat(totals.totalFor("UNKNOWN", 1))
                .isEmpty();
    }
}
~~~

Ở ví dụ này, `ordering` phụ thuộc trực tiếp `pricing` nên `DIRECT_DEPENDENCIES` cho phép bootstrap cả module đang kiểm thử và dependency trực tiếp. Điều này giúp kiểm tra **hai implementation thật giao tiếp qua API công khai**, trong phạm vi nhỏ hơn một `@SpringBootTest` toàn ứng dụng.

Nếu provider cần database, HTTP client hoặc module khác, phải cấu hình môi trường test và lựa chọn bootstrap mode theo dependency thực tế. Chuyển mọi bài test sang `ALL_DEPENDENCIES` chỉ để hết lỗi bean sẽ làm phạm vi kiểm thử lớn và kém rõ nguyên nhân lỗi.

### 6.2. Khi nào mock provider?

Trong unit test riêng của `DefaultOrderTotals`, có thể dùng fake/mock `PriceCatalog` để kiểm tra các nhánh của consumer nhanh và độc lập. Tuy nhiên:

| Mục tiêu | Cách kiểm thử |
| --- | --- |
| Logic consumer xử lý `Optional.empty()` | Unit test với fake/mock `PriceCatalog` |
| Provider thực trả đúng hợp đồng | Provider `@ApplicationModuleTest`, inject `PriceCatalog` thật |
| Consumer và provider thực tương thích | `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` hoặc integration test phù hợp |
| Quan hệ module hợp lệ | `ApplicationModules.verify()` |

Test với mock thường **không chứng minh sự tương thích runtime với provider thật**. Đừng chỉ viết consumer mock test rồi gọi đó là contract verification end-to-end.

## 7. Mở rộng API bằng @NamedInterface mà vẫn giữ ranh giới

Nếu muốn có nhiều nhóm API công khai, Spring Modulith hỗ trợ `@NamedInterface` trên package. Đây là **phương án tổ chức khác** với API mặc định ở package root trong mục 4; không áp dụng cả hai cấu trúc trùng lặp cho cùng kiểu mà không cập nhật import.

Ví dụ chuyển port sang package `pricing.spi`:

~~~text
com.example.shop.pricing
├── spi/
│   ├── package-info.java
│   ├── PriceCatalog.java
│   └── PriceQuote.java
└── internal/
    └── DefaultPriceCatalog.java
~~~

**`src/main/java/com/example/shop/pricing/spi/package-info.java`**

~~~java
@NamedInterface("quotes")
package com.example.shop.pricing.spi;

import org.springframework.modulith.NamedInterface;
~~~

Khi đó, module `ordering` dùng:

~~~java
@ApplicationModule(allowedDependencies = "pricing::quotes")
package com.example.shop.ordering;

import org.springframework.modulith.ApplicationModule;
~~~

Và consumer import `com.example.shop.pricing.spi.PriceCatalog`. Implementation `DefaultPriceCatalog` cũng import interface ở đường dẫn mới. Kết quả:

- `pricing::quotes` được công bố rõ như một phần API của `pricing`.
- `ordering` chỉ được khai báo sử dụng named interface đã thống nhất.
- `pricing.internal` vẫn là implementation và không được consumer truy cập.
- `verify()` bắt những dependency lệch hợp đồng đã cấu hình.

**Không công bố cả package persistence làm named interface** chỉ để giải quyết lỗi import. Public API nên là những hợp đồng có tính ổn định; repository, entity và business implementation không mặc nhiên là hợp đồng cho module khác.

## 8. Kiểm tra structural contract bằng ApplicationModules.verify()

Một provider/consumer test có thể xanh dù `ordering` import trực tiếp một class `public` thuộc `pricing.internal`. Vì thế, cần thêm bài architectural test.

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void public_apis_and_dependencies_are_respected() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Bài kiểm tra này xác minh mô hình dependency theo Spring Modulith, trong đó có kiểm tra:

- **Vòng phụ thuộc module:** ví dụ `ordering → pricing → ordering`.
- **Truy cập public API:** không cho `ordering` phụ thuộc vào `pricing.internal.DefaultPriceCatalog`.
- **Danh sách dependency được phép:** nếu `ordering` chỉ khai báo `pricing`, import sang module khác ngoài danh sách sẽ bị báo.
- **Named interface:** khi chuyển sang `pricing::quotes`, chỉ những package được công bố phù hợp mới được tham chiếu theo hợp đồng.

Ví dụ vi phạm:

~~~java
// Trong module ordering: không dùng kiểu nội bộ pricing.
import com.example.shop.pricing.internal.DefaultPriceCatalog;
~~~

Ngay cả khi implementation là Java `public`, Spring Modulith vẫn có thể xác định rằng nó nằm ngoài API module. Tuy nhiên `verify()` không kiểm tra giá 120,00, chính sách validation hay cấu trúc `PriceQuote`; đó là nhiệm vụ của behavioral contract test.

### Một ma trận cần kiểm tra trước khi merge

| Thay đổi trong `pricing` | Compile | Architecture verification | Behavioral contract test |
| --- | --- | --- | --- |
| Xóa method `quote(...)` | Consumer gọi method cũ thường không biên dịch | Không thay thế compiler | Không chạy được tới assertion |
| Di chuyển API vào package `internal` | Consumer có thể vẫn biên dịch nếu import cập nhật | Phát hiện truy cập trái ranh giới | Có thể xanh nếu chỉ xét kết quả |
| Đổi `Optional.empty()` thành exception | Có thể biên dịch nếu chữ ký không đổi | Có thể vẫn xanh | Bị phát hiện bởi provider/consumer test |
| Đổi đơn giá/tính tổng sai hợp đồng | Biên dịch | Xanh nếu cấu trúc hợp lệ | Test giá/total thất bại |
| Thêm vòng `pricing → ordering` | Có thể biên dịch | Phát hiện vòng dependency | Hành vi có thể vẫn xanh |
| Thêm API mới theo thiết kế được phép | Biên dịch sau khi cập nhật caller | Xanh nếu đúng ranh giới | Cần thêm ca kiểm thử hợp đồng mới |

Nhờ có các lớp kiểm tra độc lập, quality gate bảo vệ **cả cấu trúc lẫn ngữ nghĩa** của API.

## 9. Contract test cho sự kiện công khai giữa module

Không phải public API nào cũng là method đồng bộ. Module `ordering` có thể công bố sự kiện `OrderPlaced` để module `fulfillment` hoặc `notifications` phản ứng.

**Ví dụ kiểu sự kiện trong API module:**

~~~java
package com.example.shop.ordering;

import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        String customerId,
        int schemaVersion
) {}
~~~

Hợp đồng sự kiện cần làm rõ:

| Nội dung | Ví dụ ràng buộc |
| --- | --- |
| Ý nghĩa event | Đơn đã được chấp nhận theo nghiệp vụ |
| Thời điểm publish | Trong transaction khi tạo đơn; listener được cấu hình xử lý sau commit nếu cần |
| Payload | `orderId` không null, `customerId` có giá trị, version theo quy định |
| Khả năng nhận trùng | Consumer phải idempotent nếu hạ tầng có thể retry/redeliver |
| Thứ tự sự kiện | Không giả định thứ tự toàn cục nếu không có bảo đảm |
| Tương thích | Thay đổi event type/package hoặc field có thể phá consumer |
| Kết quả phía consumer | Event được nhận và side effect đúng trong module sở hữu dữ liệu |

### Producer contract test khác consumer integration test

**Producer test** có thể dùng `PublishedEvents` trong `@ApplicationModuleTest` để chứng minh module phát đúng kiểu/payload khi thực thi use case. Ví dụ khung assertion dưới đây **chỉ hoàn chỉnh khi dự án đã có port `OrderManagement` với method `placeOrder(...)` tương ứng**:

~~~java
// Trích đoạn minh họa đặt trong test @ApplicationModuleTest
// của module ordering sau khi đã cài use case placeOrder.
@Test
void publishes_public_event_contract(PublishedEvents events) {
    UUID orderId = orders.placeOrder("CUS-001");

    assertThat(events.ofType(OrderPlaced.class))
            .anySatisfy(event -> {
                assertThat(event.orderId()).isEqualTo(orderId);
                assertThat(event.customerId()).isEqualTo("CUS-001");
                assertThat(event.schemaVersion()).isEqualTo(1);
            });
}
~~~

Lưu ý đây là **trích đoạn cho tình huống mở rộng**, không thuộc các file Java đầy đủ của ví dụ báo giá `pricing` ở mục 4–6. Khi dùng thực tế, khai báo dependency JUnit/AssertJ, import `PublishedEvents` và khởi tạo đúng use case tương ứng.

**Consumer test** cần kiểm tra module nhận event và thực hiện hành vi của nó trong context phù hợp. Nếu dùng `@ApplicationModuleListener` bất đồng bộ/sau commit, hãy quan sát side effect bằng điều kiện có thời hạn, chẳng hạn Awaitility hoặc tiện ích kiểm thử kịch bản của Spring Modulith. `PublishedEvents` chỉ chứng minh **đã publish**, không chứng minh listener khác đã hoàn tất.

### Khi event đi ra broker ngoài JVM

Typed Java record phù hợp với event nội bộ chạy cùng ứng dụng. Nếu event được serialize sang Kafka/RabbitMQ hoặc HTTP callback, hợp đồng còn bao gồm JSON/Avro/Protobuf schema, header, routing key, compatibility và serialization. Khi đó cần schema/contract test chuyên biệt và integration test với broker hoặc fake server phù hợp.

**Không đồng nhất contract test Java API với consumer-driven contract testing (CDC)** cho hai service triển khai độc lập. CDC theo Pact hoặc công cụ khác thường sinh/verify hợp đồng dựa trên giao thức giữa producer–consumer; nó có mục đích liên quan nhưng phạm vi khác với module API trong một monolith.

## 10. Đổi public API thế nào để không phá consumer?

Trong một modulith, provider và consumer thường được build cùng repository, nên compiler phát hiện nhanh thay đổi chữ ký. Nhưng vẫn có những thay đổi **không làm lỗi biên dịch** mà phá hợp đồng hành vi:

- Trước đây SKU không tồn tại trả `Optional.empty()`, nay ném exception.
- Trước đây `quantity` bằng 0 bị từ chối, nay trả tổng 0.
- Trước đây đơn giá gồm thuế, nay trả giá trước thuế mà không đổi tên trường.
- Trước đây tổng tiền cố định `scale = 2`, nay đổi chính sách làm tròn khiến consumer dùng so sánh nghiêm ngặt thất bại.
- Thời điểm publish `OrderPlaced` chuyển từ sau khi transaction thành công sang một thời điểm khác.
- Event payload thay đổi kiểu hoặc ý nghĩa của `orderId`.

### Phân loại thay đổi

| Nhóm thay đổi | Ví dụ | Rủi ro |
| --- | --- | --- |
| Thêm chức năng tương thích | Thêm method mới mà client cũ không cần sử dụng | Thường có thể an toàn về hành vi nhưng cần xem tương thích source/binary |
| Thay chữ ký public | Đổi `quote(String, int)` thành `quote(Sku, long)` | Client cần thay code; có thể phá compile |
| Thay trường record | Thêm/xóa/sắp xếp component của `PriceQuote` | Có thể phá constructor, pattern matching hoặc serialization |
| Thay ngữ nghĩa | `Optional.empty()` → exception | Dễ phá hành vi dù kiểu chữ ký vẫn giống |
| Thay error contract | Chuyển `IllegalArgumentException` thành lỗi khác | Consumer có thể xử lý sai |
| Thay event schema | Đổi package, field, version | Listener/serializer/consumer có thể không tương thích |
| Tăng dependency | `pricing` bỗng import `ordering.internal` | Vi phạm chiều và phạm vi module |

**Record Java cần chú ý:** Thêm một component vào `record` làm thay đổi canonical constructor, `equals`/`hashCode` và hình dạng serialization; không coi mọi thay đổi “chỉ thêm field” là tương thích với consumer cũ.

### Quy trình thay đổi hợp đồng an toàn

1. **Xác định bên sử dụng:** API được những module nào import? Có consumer qua HTTP/broker ngoài repo không?
2. **Ghi rõ contract hiện hành:** cả chữ ký, dữ liệu, lỗi, ngữ nghĩa và thời điểm sự kiện.
3. **Thêm hoặc cập nhật test:** provider contract và consumer use-case test thể hiện hành vi mới.
4. **Ưu tiên giai đoạn chuyển tiếp:** method/DTO mới hoặc event version mới nếu cần giữ client cũ.
5. **Chạy architecture verification:** quan hệ phụ thuộc và package vẫn hợp lệ.
6. **Chạy module/integration/E2E test:** bảo đảm wiring, persistence và event phối hợp đúng.
7. **Xóa API cũ có kế hoạch:** sau khi consumer đã chuyển và chính sách tương thích cho phép.

Nếu library/API được phát hành độc lập cho khách bên ngoài, còn phải kiểm tra **binary compatibility** với artifact đã phát hành; test JUnit trong cùng source tree không đủ để chứng minh binary compatibility đó.

## 11. Khi implementation dùng database hoặc dependency khác

Ví dụ `DefaultPriceCatalog` dùng `Map` để minh họa hợp đồng. Trong hệ thống thật, provider có thể dùng `JpaRepository`, HTTP client, cache hoặc database riêng. **Contract công khai vẫn nên ổn định** trong khi implementation thay đổi.

### Provider test với JPA

Nếu API trả dữ liệu từ database:

- Seed dữ liệu có thể tái lập bằng migration/test fixture hoặc setup thích hợp.
- Dùng `@ApplicationModuleTest` với database test và bean thực để kiểm tra full provider contract.
- Thêm `@DataJpaTest` cho query/entity mapping chi tiết.
- Nếu SQL dialect, constraint hoặc transaction production quan trọng, dùng Testcontainers với loại database phù hợp.
- Tránh mock repository trong test mà mục tiêu là xác nhận cả API và dữ liệu lưu thực tế.

Nếu provider tham chiếu module khác, chọn `BootstrapMode.STANDALONE` với fake ở ranh giới hoặc mở rộng `DIRECT_DEPENDENCIES` khi hợp đồng cần dependency thật. Chỉ mở rộng bootstrap mode có chủ đích vì một contract test lớn khó cô lập nguyên nhân lỗi.

### Giao dịch và eventual consistency

API đồng bộ như `PriceCatalog.quote(...)` thường trả kết quả ngay trong lời gọi. API event có thể hứa “event được phát” nhưng kết quả downstream chỉ xuất hiện **sau commit** hoặc sau khi listener async hoàn tất.

Hai hợp đồng này không nên trộn lẫn trong cùng một assertion. Khi test event-driven integration, chờ một **điều kiện quan sát được** trong thời hạn hữu hạn; không dùng `Thread.sleep(...)` cố định và không mặc định `PublishedEvents` chứng minh giao nhận bền vững, retry hoặc consumer đã xử lý xong.

## 12. Lỗi phổ biến khi viết contract test

| Triệu chứng hoặc kiểu sai | Tại sao sai | Cách khắc phục |
| --- | --- | --- |
| Provider test mock chính `PriceCatalog` | Chỉ xác nhận dữ liệu mock đã lập trình | Inject implementation thật của provider |
| Test gọi trực tiếp `DefaultPriceCatalog` từ consumer | Consumer bị ghép vào implementation nội bộ | Chỉ import `PriceCatalog` và `PriceQuote` công khai |
| Chỉ kiểm tra không ném exception | Bỏ sót dữ liệu trả sai, null và semantics | Assert đủ field và tình huống biên |
| Chỉ có `verify()` | Kiểm tra cấu trúc, không kiểm tra nghiệp vụ | Thêm provider/consumer contract test |
| Chỉ có provider test | Consumer có thể dùng API sai hoặc cần behavior khác | Thêm consumer-facing test cho use case quan trọng |
| Hard-code dữ liệu production vào test | Dễ thay đổi ngoài kiểm soát hoặc mang thông tin không nên có | Dùng fixture test riêng, hợp đồng rõ |
| Mở rộng `ALL_DEPENDENCIES` vô điều kiện | Test chậm và dễ bị ảnh hưởng bởi module không liên quan | Chọn bootstrap mode tối thiểu đủ hợp đồng |
| Đổi public record nhưng không cập nhật test consumer | Có thể phá tạo đối tượng/serialization | Kiểm tra source, binary, semantics và schema |
| Chỉ kiểm tra event đã publish | Chưa chứng minh listener đã chạy | Thêm integration test sau commit |
| Tắt rule architecture để test xanh | Che vi phạm ranh giới module | Sửa dependency hoặc thay đổi kiến trúc có review |

**Dấu hiệu của contract test tốt:** tên test nói rõ hành vi public API; test khởi tạo dependency tối thiểu nhưng dùng provider thật ở nơi cần kiểm chứng; mỗi assertion quan sát output/exceptions từ API; và khi thay đổi sai hợp đồng, test thất bại có ý nghĩa.

## 13. Quality gate CI cho public module API

Một CI pipeline cho Spring Modulith nên kết hợp các lớp kiểm tra theo chi phí và mục tiêu:

~~~mermaid
flowchart LR
    PR["Pull request"] --> C["Compile và unit tests"]
    C --> A["ApplicationModules.verify()"]
    A --> P["Provider contract tests"]
    P --> U["Consumer contract tests"]
    U --> I["Module/integration tests"]
    I --> G{"Tất cả gate<br/>bắt buộc xanh?"}
    G -- "Có" --> M["Cho phép merge"]
    G -- "Không" --> F["Sửa lỗi hợp đồng"]
~~~

| Gate | Lỗi được nhắm tới | Tốc độ tương đối |
| --- | --- | --- |
| Compile/test compilation | API không còn type/method tương thích tại source | Nhanh |
| Architectural test | Import nội bộ, vòng dependency, whitelist sai | Thường nhanh |
| Unit tests | Logic pure Java và validation | Nhanh |
| Provider contract test | Ngữ nghĩa API công khai sai | Nhanh đến vừa tùy Spring context |
| Consumer integration test | Module sử dụng API thực không đúng | Vừa |
| Integration/E2E test | Database, transaction, event và HTTP boundary sai | Có thể chậm hơn |

**Yêu cầu quan trọng của pipeline:**

- Chạy `ModuleArchitectureTest` và các contract test bắt buộc trên pull request.
- Nếu tách test suite, cấu hình include/tag/JUnit discovery để không vô tình bỏ sót test kiến trúc hoặc consumer.
- Khi lỗi xảy ra, log cần cho biết API, module, input, expected/actual và dependency bị vi phạm.
- Test dữ liệu phải độc lập thứ tự chạy; môi trường database/container nếu có phải tái lập được.
- Khi sửa public API, review các consumer và event/REST schema chịu ảnh hưởng; test xanh ở provider chưa đủ.
- Chỉ cho phép merge khi những job bắt buộc đều xanh theo chính sách dự án.

Với Gradle thông thường, các test JUnit có thể chạy bằng `./gradlew test` khi cấu hình JUnit Platform đã phù hợp. Trên Windows dùng wrapper `gradlew.bat test`. Nếu integration test được tách task, CI phải thực thi task đó theo yêu cầu quality gate.

## 14. Bài thực hành

### Bài A — Contract test cho provider

Triển khai `PriceCatalog` và `PriceQuote` như ở mục 4. Viết `PriceCatalogContractTest` với ít nhất các ca:

1. SKU tồn tại và số lượng hợp lệ → đúng `unitPrice`, `quantity`, `total`.
2. SKU không tồn tại → `Optional.empty()`.
3. Số lượng 0/âm → `IllegalArgumentException`.
4. SKU null/rỗng → lỗi theo hợp đồng.
5. Tổng tiền của nhiều số lượng không có sai số do dùng `double`.

**Tiêu chí đạt:** Sửa cố ý phép tính `total` hoặc giá trị trả về khi SKU không tồn tại phải làm test đỏ.

### Bài B — Kiểm tra consumer sử dụng đúng public API

Triển khai `OrderTotals` và `DefaultOrderTotals`; không import `pricing.internal`. Dùng `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` để kiểm thử contract qua module `ordering`. Xác nhận module trả đúng tổng và xử lý được SKU không tồn tại.

### Bài C — Đánh gãy hợp đồng có kiểm soát

Trong nhánh thực hành, tạm đổi:

- `Optional.empty()` thành ngoại lệ cho SKU không tìm thấy.
- `PriceQuote.total` thành giá chưa nhân số lượng.
- `PriceQuote` bổ sung một trường mà không cập nhật consumer.

Đối với mỗi thay đổi, dự đoán lỗi ở **compile**, **architecture verification** hay **behavioral contract test**, sau đó chạy kiểm tra và khôi phục mã đúng hợp đồng.

### Bài D — Named interface và whitelist

Chuyển API của `pricing` sang `pricing.spi`, khai báo `@NamedInterface("quotes")` và `@ApplicationModule(allowedDependencies = "pricing::quotes")` tại `ordering`. Chạy `ApplicationModules.verify()`, sau đó thử import implementation `pricing.internal` để thấy architectural test thất bại.

### Bài E — Event contract

Giả sử `ordering` phát `OrderPlaced` và `fulfillment` lắng nghe. Viết hai bài test tách biệt: provider test xác nhận payload sự kiện đã publish, consumer/integration test xác nhận side effect của listener sau commit. Giải thích tại sao event được publish không đồng nghĩa đã xử lý hoặc giao nhận bền vững.

### Câu hỏi tự đánh giá

- Vì sao `public class` ở `pricing.internal` không nên được `ordering` import?
- Có trường hợp nào Java code biên dịch được nhưng behavioral contract bị phá? Cho hai ví dụ.
- `ApplicationModules.verify()` có đảm bảo `quote(...)` tính đúng tổng không?
- Provider contract test dùng mock chính provider có giá trị chứng minh gì?
- Đổi event record nhưng giữ nguyên tên class có luôn tương thích không?
- Khi nào kiểm thử bằng `@ApplicationModuleTest` đủ, khi nào cần test database/event/HTTP tích hợp?

## 15. Ghi nhớ

**Contract test cho public API của module** bảo vệ điều provider cam kết với consumer: chữ ký, dữ liệu, kết quả, lỗi và ý nghĩa nghiệp vụ. Với Spring Modulith, hãy viết provider test trên **interface công khai với implementation thật**, thêm consumer-facing test cho các luồng sử dụng trọng yếu và kiểm tra ranh giới bằng `ApplicationModules.verify()`. `@NamedInterface` giúp công bố API theo nhóm; `allowedDependencies` xác định module nguồn được phép sử dụng API nào.

Hãy giữ JPA entity, repository và business implementation trong package nội bộ; đừng xem Java `public` là sự cho phép xuyên module. Với event, kiểm tra riêng việc publish, xử lý sau commit và độ tin cậy giao nhận. Khi kết hợp contract, architecture, module, database và integration tests trong **quality gate CI**, ứng dụng vừa duy trì được ranh giới kiến trúc, vừa phát hiện sớm sự thay đổi làm hỏng hành vi consumer.
