# Thay đổi API và ảnh hưởng kiểm thử cấu trúc

Trong Spring Modulith, API của một application module không chỉ gồm các phương thức Java có thể gọi được. API còn được xác định bởi **package nào được công bố**, **named interface nào sở hữu các kiểu công khai** và **module tiêu thụ nào được phép phụ thuộc vào chúng**. Vì thế, một thay đổi tưởng như đơn giản — đổi tên named interface, di chuyển DTO, thêm một class public hoặc sửa chữ ký facade — có thể ảnh hưởng đến cả mã biên dịch, quan hệ phụ thuộc kiến trúc và hành vi nghiệp vụ.

Bài thuộc chương **Named interfaces** của lộ trình **SPRING_MODULITH_VERIFICATION_TESTING**. Mục tiêu là đánh giá tác động thay đổi API, kiểm chứng ranh giới bằng `ApplicationModules.verify()`, bổ sung `@ApplicationModuleTest`, kiểm thử sự kiện, cơ sở dữ liệu và tích hợp, rồi đưa các phép kiểm tra vào **quality gate trong CI** để ngăn phụ thuộc sai và hồi quy.

> **Nguyên tắc:** Một lần chạy `ApplicationModules.verify()` thành công chỉ chứng minh mô hình phụ thuộc hiện tại thỏa các quy tắc kiến trúc được hỗ trợ; nó không tự kết luận thay đổi API tương thích với phiên bản cũ, đúng nghiệp vụ hay giữ nguyên dữ liệu.

## 1. API module gồm những lớp hợp đồng nào?

Xét một ứng dụng Spring Boot có application module `catalog` cung cấp báo giá và `checkout` sử dụng báo giá. Trong một **closed application module**, những kiểu public ở package gốc thuộc **API mặc định**; các kiểu trong subpackage được coi là nội bộ nếu chưa được công bố bằng named interface hoặc cơ chế tương ứng.

```text
com.acme.shop
├── ShopApplication.java
├── catalog/
│   ├── api/
│   │   └── pricing/
│   │       ├── package-info.java       ← @NamedInterface("pricing")
│   │       ├── PriceLookup.java        ← hợp đồng truy vấn
│   │       └── PriceQuote.java         ← kiểu dữ liệu công bố
│   └── internal/
│       ├── ProductEntity.java
│       ├── PriceRepository.java
│       └── DefaultPriceLookup.java
└── checkout/
    ├── package-info.java               ← allowedDependencies = "catalog::pricing"
    └── CheckoutPricingService.java
```

Có **ba lớp cần xem xét** khi thay đổi API:

| Lớp hợp đồng | Nội dung | Ví dụ thay đổi |
| --- | --- | --- |
| **Java API** | Tên package, class, method, record component và chữ ký public | Đổi `PriceLookup.findBySku` thành `findQuote` |
| **API kiến trúc** | Những kiểu được công bố qua API mặc định hoặc `@NamedInterface` | Đổi `pricing` thành `offers` |
| **Quy tắc tiêu thụ** | `allowedDependencies` của module sử dụng | `checkout` chuyển từ `catalog::pricing` sang `catalog::offers` |

Một thay đổi có thể tác động nhiều lớp cùng lúc. Ví dụ di chuyển `PriceQuote` từ `catalog.api.pricing` sang `catalog.internal` vừa làm đổi tên lớp đầy đủ (*fully qualified name*), vừa đưa một kiểu vốn thuộc API ra khỏi phần được công bố.

### Ví dụ cấu hình ban đầu

Ở module cung cấp:

```java
// catalog/api/pricing/package-info.java
/**
 * Hợp đồng tra cứu báo giá công khai của module catalog.
 *
 * <p>Chỉ chứa API tra cứu và DTO, không chứa entity hoặc repository.
 */
@org.springframework.modulith.NamedInterface("pricing")
package com.acme.shop.catalog.api.pricing;
```

```java
// catalog/api/pricing/PriceQuote.java
package com.acme.shop.catalog.api.pricing;

import java.math.BigDecimal;
import java.util.Currency;

public record PriceQuote(
        String sku,
        BigDecimal amount,
        Currency currency
) {}
```

```java
// catalog/api/pricing/PriceLookup.java
package com.acme.shop.catalog.api.pricing;

import java.util.Optional;

public interface PriceLookup {
    Optional<PriceQuote> findBySku(String sku);
}
```

Ở module tiêu thụ:

```java
// checkout/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::pricing"
)
package com.acme.shop.checkout;
```

```java
// checkout/CheckoutPricingService.java
package com.acme.shop.checkout;

import com.acme.shop.catalog.api.pricing.PriceLookup;
import com.acme.shop.catalog.api.pricing.PriceQuote;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CheckoutPricingService {

    private final PriceLookup prices;

    public CheckoutPricingService(PriceLookup prices) {
        this.prices = prices;
    }

    public Optional<PriceQuote> quoteFor(String sku) {
        return prices.findBySku(sku);
    }
}
```

Giả định `catalog.internal` cung cấp một Spring bean hiện thực `PriceLookup`. Phần triển khai và repository không cần xuất hiện trong mã của `checkout`. Với các cấu hình trên, quan hệ từ `checkout` tới `catalog::pricing` là hợp đồng kiến trúc được chủ động cho phép.

## 2. Ba loại lỗi sau khi thay đổi API

Khi CI thất bại, cần xác định **kiểu bảo đảm nào đã bị phá vỡ** trước khi sửa.

| Loại lỗi | Phát hiện bằng gì? | Ví dụ | Điều không được suy luận |
| --- | --- | --- | --- |
| **Biên dịch** | `javac`, Maven/Gradle compile | Đổi tên `findBySku` nhưng service tiêu thụ vẫn gọi tên cũ | Lỗi biên dịch chưa chắc là lỗi `ApplicationModules.verify()` |
| **Kiến trúc** | `ApplicationModules.verify()` trong test JUnit | `checkout` tham chiếu kiểu `catalog.internal` hoặc named interface chưa được cấp phép | PASS không có nghĩa API không bị mở rộng vô ý |
| **Hành vi** | Unit, `@ApplicationModuleTest`, event, database và integration test | `findBySku` vẫn biên dịch nhưng trả giá sai hoặc sai đơn vị tiền | PASS kiến trúc không chứng minh transaction và dữ liệu đúng |

Ví dụ, đổi `@NamedInterface("pricing")` thành `@NamedInterface("offers")` nhưng giữ package và lớp Java có thể **vẫn biên dịch**. Tuy nhiên, `checkout` vẫn khai báo `allowedDependencies = "catalog::pricing"`, nên quyền phụ thuộc không còn phù hợp với tên API được công bố. Test kiến trúc cần phát hiện sai lệch đó.

Ngược lại, nếu `PriceLookup.findBySku` bắt đầu trả giá chưa gồm thuế thay vì giá cuối cùng nhưng **giữ nguyên chữ ký**, phép kiểm chứng kiến trúc không thể tự nhận biết hợp đồng nghiệp vụ đã thay đổi. Trường hợp này đòi hỏi test hành vi có kỳ vọng về thuế và đơn vị tiền.

## 3. Thay đổi tên named interface

### Tình huống: `pricing` thành `offers`

Ban đầu, package `catalog.api.pricing` khai báo:

```java
@org.springframework.modulith.NamedInterface("pricing")
package com.acme.shop.catalog.api.pricing;
```

Nhóm phát triển quyết định tên `offers` phản ánh hợp đồng mới tốt hơn:

```java
@org.springframework.modulith.NamedInterface("offers")
package com.acme.shop.catalog.api.pricing;
```

Dù package Java vẫn là `catalog.api.pricing`, **tên kiến trúc** đã đổi từ `catalog::pricing` sang `catalog::offers`. Các module tiêu thụ hiện có cần được xem xét đồng bộ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::offers"
)
package com.acme.shop.checkout;
```

Các bước tác động:

1. Xác định module nào đang tham chiếu `catalog::pricing` trong `allowedDependencies`.
2. Đánh giá liệu giao diện thực sự đổi ý nghĩa hay chỉ đổi tên. Nếu chỉ tài liệu khó hiểu, đôi khi sửa JavaDoc ít gây ảnh hưởng hơn.
3. Cập nhật annotation ở module cung cấp và danh sách quyền ở **tất cả module tiêu thụ liên quan** trong cùng thay đổi có kiểm soát.
4. Chạy biên dịch, `ApplicationModules.verify()` và các test hành vi liên quan.
5. Cập nhật tài liệu kiến trúc và ví dụ mã để người tiêu thụ không tiếp tục dùng tên cũ.

Đừng chỉ đổi tên `package-info.java` hoặc tên folder rồi mặc định `allowedDependencies` tự cập nhật. Giá trị `"catalog::pricing"` là một **chuỗi cấu hình**, không được Java tự refactor như symbol import.

### Tình huống: đổi cả package Java

Nếu chuyển `PriceLookup`, `PriceQuote` từ `catalog.api.pricing` sang `catalog.api.offers`, tên đầy đủ của các kiểu Java cũng đổi. Khi đó có thêm tác động:

- Các import ở `checkout` và module khác phải sửa để mã biên dịch.
- File `package-info.java` phải nằm trong **đúng package mới** và khai báo đúng `package com.acme.shop.catalog.api.offers;`.
- Nếu named interface vẫn tên `pricing`, quyền cấu hình có thể **không cần đổi**, miễn mô hình module vẫn công bố đúng `pricing`. Tên package Java và tên named interface là hai khái niệm độc lập.
- Nếu cả tên kiến trúc cũng đổi, phải cập nhật thêm `allowedDependencies`.

**Kết luận cho trường hợp này:** thay đổi package và thay đổi tên named interface là hai trục khác nhau, cần kiểm tra riêng từng trục.

## 4. Di chuyển hoặc rút một kiểu khỏi API công bố

Giả sử nhóm phát triển cho rằng `PriceQuote` là chi tiết nội bộ và di chuyển nó vào `catalog.internal`, nhưng `PriceLookup` vẫn trả về kiểu đó:

```java
// Ví dụ SAI về ranh giới hợp đồng
package com.acme.shop.catalog.api.pricing;

import com.acme.shop.catalog.internal.PriceQuote;
import java.util.Optional;

public interface PriceLookup {
    Optional<PriceQuote> findBySku(String sku);
}
```

Lúc này người tiêu thụ `PriceLookup` bị kéo theo một kiểu thuộc phần **không được công bố** của closed module. Dù triển khai có thể biên dịch, thiết kế đã rò rỉ kiểu nội bộ qua chữ ký public.

Để sửa, giữ một DTO hợp đồng `PriceQuote` trong API `pricing` và thực hiện mapping từ entity/DTO nội bộ **bên trong `catalog`**. Trường hợp `PriceQuote` thực sự không còn được người tiêu thụ cần đến, hãy thay chữ ký bằng hợp đồng mới có chủ đích và cập nhật các module tiêu thụ cùng test.

Một checklist nhỏ khi chuyển kiểu khỏi package API:

| Cần kiểm tra | Nguy cơ |
| --- | --- |
| Có code tiêu thụ import trực tiếp kiểu không? | Lỗi biên dịch, phải sửa import/chữ ký |
| Kiểu còn xuất hiện trong generic, tham số, `throws` hoặc kiểu trả về public không? | Lộ chi tiết nội bộ qua hợp đồng còn tồn tại |
| Các public type khác có kế thừa hoặc dùng annotation tham chiếu kiểu đó không? | Phụ thuộc gián tiếp vẫn tồn tại |
| Người tiêu thụ còn được phép tham chiếu API mới không? | Vi phạm `allowedDependencies` |
| DTO/event có thay đổi ý nghĩa dữ liệu không? | Hồi quy hành vi dù test kiến trúc PASS |

**Không sửa bằng cách đánh dấu `catalog.internal` là một named interface lớn**. Việc đó mở thêm nhiều chi tiết triển khai và làm suy yếu ranh giới cần bảo vệ.

## 5. Thay đổi chữ ký facade, interface và DTO

Không phải mọi thay đổi API đều cần sửa `@NamedInterface`. Ví dụ, nhóm phát triển mở rộng hợp đồng tra cứu giá:

```java
// Trước
Optional<PriceQuote> findBySku(String sku);

// Sau
Optional<PriceQuote> findBySku(String sku, String customerSegment);
```

Việc này có thể khiến các nơi gọi cũ hoặc lớp hiện thực của `PriceLookup` **không biên dịch**, trong khi package vẫn được công bố là `catalog::pricing` và các quy tắc `allowedDependencies` vẫn hợp lệ.

Với Java `record`, sửa cấu trúc cũng có ảnh hưởng tương tự:

```java
// Trước
public record PriceQuote(String sku, BigDecimal amount, Currency currency) {}

// Sau: bổ sung thuế và thay đổi constructor chính của record
public record PriceQuote(
        String sku,
        BigDecimal amount,
        Currency currency,
        BigDecimal taxAmount
) {}
```

Các đoạn `new PriceQuote(sku, amount, currency)` trong mã cũ có thể lỗi biên dịch vì constructor canonical đã có tham số mới. JSON serialization, dữ liệu sự kiện hoặc các test so sánh record cũng có thể bị ảnh hưởng tùy cách sử dụng.

### Phân loại thay đổi theo mức ảnh hưởng

| Thay đổi | Kiểm tra tối thiểu | Ghi chú |
| --- | --- | --- |
| Thêm method abstract vào interface public | Compile implementation + caller, test module | Implementation cũ phải đáp ứng method mới |
| Thêm method `default` | Compile + test hành vi | Có thể tương thích nguồn, nhưng mặc định mới vẫn cần kiểm chứng |
| Xóa/đổi tên method | Compile toàn bộ module liên quan | Caller cũ có nguy cơ bị lỗi |
| Đổi record component hoặc kiểu kết quả | Compile, serialization/event test, integration test | Constructor và schema dữ liệu có thể đổi |
| Đổi ý nghĩa của tham số nhưng giữ chữ ký | Contract test, test nghiệp vụ, review | `verify()` không nhận biết ý nghĩa |
| Thêm `public` class vào package có `@NamedInterface` | Review bề mặt API, test kiến trúc | `verify()` có thể vẫn PASS dù API mở rộng ngoài ý muốn |

**Phân biệt tương thích ở các cấp:** một thay đổi có thể biên dịch được trong repository hiện tại nhưng không tương thích với client bên ngoài được biên dịch trước đó; Spring Modulith chủ yếu giải quyết **kiến trúc bên trong ứng dụng**. Nếu module được đóng gói thành thư viện riêng cho người tiêu thụ ngoài repository, có thể cần công cụ kiểm tra tương thích binary/source và chính sách phiên bản API.

## 6. Mở rộng API công khai mà test kiến trúc vẫn PASS

Giả sử một người thêm `PriceRepository` vào chính package đã công bố `catalog.api.pricing` để tiện dùng. Tên named interface và `allowedDependencies` không đổi. Module `checkout` có thể bắt đầu phụ thuộc vào repository mà phép kiểm chứng kiến trúc **không nhất thiết báo vi phạm**, vì lớp đó hiện nằm trong bề mặt API đã được đánh dấu.

Đây là trường hợp quan trọng: **test kiến trúc kiểm tra tính hợp lệ theo mô hình đã khai báo, không đánh giá chất lượng lựa chọn công bố**.

Để tránh mở rộng API không chủ đích:

1. Giữ package của named interface chỉ gồm các hợp đồng cần thiết như interface, DTO hoặc event.
2. Đặt repository/entity/adapter ở subpackage nội bộ của module cung cấp.
3. Khi xuất hiện kiểu `public` mới trong API, review lý do module khác cần kiểu đó.
4. Kiểm tra chữ ký public không làm lộ các kiểu nội bộ hoặc dữ liệu nhạy cảm.
5. Với hệ thống cần chính sách chặt hơn, bổ sung kiểm tra riêng cho danh sách kiểu API được phép công bố; không giả định `verify()` thực hiện kiểm tra nghiệp vụ này.

Một thay đổi **nới `allowedDependencies`** cũng có thể khiến test kiến trúc PASS mà không chứng minh đó là thiết kế phù hợp. Ví dụ chuyển từ `catalog::pricing` sang một quyền rộng hơn phải có lý do về người tiêu thụ thực tế, không phải cách né lỗi bằng cách mở quyền tùy ý.

## 7. Kiểm chứng bằng `ApplicationModules.verify()`

Tạo một test JUnit ở package ứng dụng:

```java
// src/test/java/com/acme/shop/ModulithArchitectureTest.java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTest {

    @Test
    void verifiesPublishedApisAndDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là lớp `@SpringBootApplication` ở `com.acme.shop`, bao quanh các module. Đây là test kiến trúc **cho toàn bộ mô hình application module** được phát hiện, không chỉ module `catalog` hoặc `checkout`.

`verify()` thực hiện các kiểm chứng cấu trúc quan trọng, bao gồm phát hiện chu trình phụ thuộc, phụ thuộc từ module khác vào phần **không công bố** của closed module, và vi phạm danh sách `allowedDependencies`. Test cần dependency Spring Modulith/JUnit phù hợp nhưng không phải khởi động toàn bộ `ApplicationContext` hoặc kết nối database chỉ để phân tích kiến trúc.

### Ma trận thay đổi và kết quả mong đợi

| Thí nghiệm | Thay đổi tạm thời | Kết quả kiểm chứng mong đợi |
| --- | --- | --- |
| **A — Baseline** | `checkout` dùng `PriceLookup` và `PriceQuote` qua `catalog::pricing` | PASS nếu không có vi phạm khác |
| **B — Đổi tên giao diện lệch phía tiêu thụ** | Đổi `@NamedInterface("pricing")` thành `@NamedInterface("offers")`, giữ `allowedDependencies = "catalog::pricing"` | FAIL: cấu hình quyền và API được công bố không còn khớp |
| **C — Rút công bố** | Xóa `@NamedInterface` khỏi `catalog.api.pricing` nhưng `checkout` vẫn phụ thuộc các kiểu đó | FAIL: subpackage không còn là API được công bố |
| **D — Truy cập implementation** | `checkout` dùng một class `public` ở `catalog.internal` | FAIL: phụ thuộc vào phần nội bộ |
| **E — Sai interface** | `checkout` dùng kiểu thuộc `catalog::events` nhưng chỉ được phép dùng `pricing` | FAIL: vượt `allowedDependencies` |
| **F — Đổi nghĩa giá** | Giữ chữ ký, nhưng implementation tính giá sai hoặc bỏ thuế | `verify()` có thể PASS; test hành vi phải báo lỗi |
| **G — Công bố dư** | Thêm một repository public vào package `catalog.api.pricing` | `verify()` có thể PASS; cần review/kiểm tra danh mục API |
| **H — Khôi phục hợp đồng** | Giữ đúng named interface, imports và quyền phụ thuộc | PASS nếu toàn bộ kiến trúc hợp lệ |

**Lưu ý về thí nghiệm:** để kiểm tra lỗi kiến trúc ở D, class nội bộ phải đủ `public` cho Java biên dịch và phải được **tham chiếu thực sự** trong field, constructor, chữ ký hoặc lời gọi. Chỉ thêm một `import` không sử dụng có thể không tạo ra phụ thuộc được công cụ phân tích nhìn thấy. Nếu class là package-private thì lỗi biên dịch xảy ra trước khi test kiến trúc chạy.

Không đưa mã vi phạm cố ý vào nhánh chính. Sau mỗi thí nghiệm, khôi phục trạng thái hợp lệ và chạy lại test. Các kết quả trong bảng là **kỳ vọng theo mô hình ví dụ**, chưa phải log đã chạy trên một repository cụ thể.

## 8. Kiểm thử hành vi và dữ liệu sau thay đổi API

Một API được công bố hợp lệ vẫn có thể chạy sai. Khi thay chữ ký hoặc ngữ nghĩa `PriceLookup`, cần mở rộng kiểm thử theo loại thay đổi.

| Loại test | Trách nhiệm | Ví dụ sau thay đổi API |
| --- | --- | --- |
| **Unit test** | Logic biến đổi giá, trạng thái, validation | Giá theo `customerSegment` và thuế có đúng không? |
| **`@ApplicationModuleTest`** | Khởi tạo module và kiểm tra bean/hành vi trong phạm vi module | `PriceLookup` vẫn có implementation sau refactor? |
| **Database/integration test** | Truy vấn, mapping, transaction và migration | `PriceQuote` mới ánh xạ dữ liệu từ persistence đúng không? |
| **Event test** | Sự kiện được phát/nhận với payload và ngữ nghĩa đúng | Nếu giá đổi, `PriceChanged` có schema được người nghe xử lý đúng không? |
| **Test tích hợp liên module** | `checkout` sử dụng `catalog` qua hợp đồng thật | Giá cuối cùng dùng để tạo đơn có đúng không? |
| **Architecture test** | Phụ thuộc tuân thủ API/named interface và không tạo chu trình | `checkout` vẫn chỉ dùng `catalog::pricing` |

Ví dụ kiểm tra một module cung cấp bean hợp đồng:

```java
// src/test/java/com/acme/shop/catalog/CatalogModuleTest.java
package com.acme.shop.catalog;

import com.acme.shop.catalog.api.pricing.PriceLookup;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class CatalogModuleTest {

    @Autowired
    PriceLookup prices;

    @Test
    void providesPublicPricingContract() {
        assertThat(prices).isNotNull();
    }
}
```

Test ví dụ giả định `catalog` có bean hiện thực `PriceLookup` và ngữ cảnh kiểm thử được cấu hình phù hợp, bao gồm test datasource nếu implementation cần database. Nó phát hiện **sự cố bean wiring** sau refactor nhưng chưa đủ để xác nhận giá đúng.

### Đối với sự kiện công bố qua named interface

Nếu `catalog` còn có `@NamedInterface("events")` chứa `PriceChanged`, việc đổi record payload hoặc chuyển package của event có thể ảnh hưởng các listener ở module khác. Khi đó:

- Rà soát named interface và `allowedDependencies` của module nghe sự kiện.
- Biên dịch mọi listener tham chiếu kiểu event.
- Test phát đúng event, đúng dữ liệu, đúng thời điểm giao dịch và xử lý lỗi.
- Kiểm tra idempotency, xử lý trùng hoặc cơ chế giao nhận lại nếu luồng thực tế có khả năng chạy lại.

`verify()` kiểm tra **quan hệ phụ thuộc đến kiểu sự kiện**, không chứng minh event đã được phát hoặc listener chạy đúng.

## 9. Quy trình kiểm tra tác động trước khi hợp nhất

Để quản lý an toàn một thay đổi API, hãy thực hiện theo thứ tự:

1. **Nêu rõ lý do:** thay đổi tên vì dễ hiểu hơn, cần chức năng mới, hay cần tách trách nhiệm giữa các module?
2. **Chụp hiện trạng hợp đồng:** tên module, named interface, các kiểu public, chữ ký và danh sách module tiêu thụ.
3. **Xác định phạm vi thay đổi:** package/type Java, `@NamedInterface`, `allowedDependencies`, dữ liệu sự kiện và API mặc định có bị ảnh hưởng không?
4. **Đánh giá tương thích:** caller cũ có biên dịch được không; test data, JSON payload hoặc tác dụng phụ có thay đổi không?
5. **Cập nhật đồng bộ:** code bên cung cấp, code tiêu thụ, quy tắc phụ thuộc, tài liệu và test liên quan.
6. **Chạy quality gate:** compile, `ApplicationModules.verify()`, `@ApplicationModuleTest`, event/database/integration tests phù hợp.
7. **Review phạm vi công bố:** thay đổi có đưa repository, entity hoặc helper vào package API không; có nới quyền chỉ để hết lỗi test không?
8. **Khóa hồi quy trong CI:** đảm bảo việc vi phạm ranh giới hoặc test hành vi thất bại khiến pipeline thất bại.

Một phương pháp code review hữu ích là viết ra **trước và sau** cho các hợp đồng thay đổi:

| Thuộc tính | Trước | Sau |
| --- | --- | --- |
| Named interface | `catalog::pricing` | `catalog::offers` |
| Package chứa API | `catalog.api.pricing` | `catalog.api.pricing` (giữ nguyên) |
| Public types | `PriceLookup`, `PriceQuote` | Giữ nguyên |
| Quyền của `checkout` | `catalog::pricing` | `catalog::offers` |
| Phần cần kiểm tra | Kiến trúc hiện tại | Đồng bộ tên, `verify()`, test hành vi |

Bảng trên thể hiện một **đổi tên kiến trúc thuần túy**; nếu đồng thời chuyển package, cần bổ sung thay đổi import và chữ ký. Với một codebase lớn, cách theo dõi có cấu trúc giúp tránh bỏ sót module tiêu thụ.

## 10. CI quality gate: test nào chặn thay đổi nào?

Tối thiểu, chạy test kiến trúc trong suite JUnit thường xuyên:

```bash
./gradlew test
```

Với Windows dùng wrapper phù hợp; với Maven có thể chạy:

```bash
mvn test
```

Một pipeline thực tế có thể chia các bước compile, architecture test, module test và integration test, nhưng **tất cả điều kiện bắt buộc phải có kết quả PASS trước khi chấp nhận thay đổi**. Việc chia job nhằm tối ưu tốc độ, không làm giảm phạm vi kiểm tra ranh giới.

Ví dụ quy tắc:

- **Compile FAIL:** dừng nếu mã tiêu thụ còn import kiểu/method cũ.
- **Architecture FAIL:** dừng nếu `allowedDependencies` không khớp giao diện đã công bố, có phụ thuộc vào `internal` hoặc có vòng phụ thuộc.
- **Behavior FAIL:** dừng nếu DTO, transaction, event, dữ liệu hoặc logic báo giá không đáp ứng hợp đồng mới.
- **Review chưa đạt:** xem xét lại nếu API public rộng hơn nhu cầu, dù tất cả test kỹ thuật PASS.

Không nên “khắc phục” một lỗi bằng cách xóa `verify()`, chuyển toàn bộ module thành open hoặc mở rộng `allowedDependencies` vô điều kiện. Những hành động đó làm mất chất lượng ranh giới mà quality gate đang bảo vệ.

## 11. Bài thực hành: đổi tên API mà không phá kiến trúc

### Bối cảnh

Module `catalog` công bố `catalog::pricing`; module `checkout` chỉ được phụ thuộc vào phần API đó. Nhóm phát triển muốn đổi tên named interface thành `offers`, đồng thời xem xét bổ sung thông tin thuế vào `PriceQuote`.

### Các bước thực hiện

1. **Dựng baseline:** tạo `PriceLookup`, `PriceQuote`, `catalog/api/pricing/package-info.java` và `checkout/package-info.java` như ví dụ. Chạy `ApplicationModules.of(ShopApplication.class).verify()`.
2. **Đổi tên một phía:** chỉ đổi `@NamedInterface("pricing")` thành `@NamedInterface("offers")`; giữ `checkout` dùng `catalog::pricing`. Chạy lại test kiến trúc, ghi nhận nguyên nhân sai lệch.
3. **Đồng bộ người tiêu thụ:** sửa `allowedDependencies` thành `catalog::offers`, giữ nguyên các Java import; kiểm chứng trở lại trạng thái hợp lệ.
4. **Tạo lỗi Java API:** đổi tên `findBySku` thành `findQuote` trong `PriceLookup` nhưng chưa sửa code tiêu thụ/implementation. Chạy compile và giải thích vì sao đây là lỗi khác với ràng buộc named interface.
5. **Sửa đồng bộ chữ ký:** cập nhật caller và implementation, chạy lại compile và `verify()`.
6. **Thay DTO:** thêm `taxAmount` vào `PriceQuote`, cập nhật chỗ tạo record và test dữ liệu. Giải thích vì sao test kiến trúc không đủ xác nhận số thuế đúng.
7. **Tạo lỗi công bố:** tạm chuyển `PriceQuote` vào `catalog.internal` nhưng để kiểu đó xuất hiện trong chữ ký của `PriceLookup`; phân tích phụ thuộc rò rỉ và đưa DTO trở lại phần API.
8. **Thử mở rộng API vô ý:** thêm một kiểu `public` không phục vụ người tiêu thụ vào package `catalog.api.pricing`. Xem vì sao cần code review hoặc kiểm tra danh mục API ngay cả khi `verify()` PASS.
9. **Khôi phục và chốt:** hoàn tất code, `@NamedInterface`, `allowedDependencies`, test module/event/database/integration cần thiết; khóa quy tắc trong CI.

### Câu hỏi tự đánh giá

**1. Đổi `@NamedInterface("pricing")` thành `@NamedInterface("offers")` có bắt buộc đổi package Java không?** Không. Tên kiến trúc và tên package Java là hai khái niệm khác nhau; chỉ cần đồng bộ các quyền phụ thuộc liên quan.

**2. Khi xóa `@NamedInterface` khỏi subpackage nhưng vẫn giữ class `public`, vì sao có thể lỗi kiến trúc?** Vì subpackage đó không còn là API được công bố của closed module, dù Java vẫn có thể cho import.

**3. Vì sao thêm record component có thể làm compile FAIL nhưng `verify()` không phải công cụ chính để chẩn đoán?** Vì thay đổi constructor/chữ ký là vấn đề tương thích Java API, cần compile và test hành vi.

**4. Vì sao thêm repository public vào package named interface có thể vẫn PASS?** Vì công cụ thấy một kiểu nằm trong API đã công bố; đánh giá kiểu đó có **nên** được công bố là trách nhiệm của thiết kế/review và kiểm tra riêng.

**5. Khi thay đổi ý nghĩa giá nhưng không đổi chữ ký, test nào phát hiện?** Test nghiệp vụ, database/tích hợp và contract test với các trường hợp dữ liệu rõ ràng; `verify()` không diễn giải nghĩa của giá.

## 12. Ghi nhớ

**Thay đổi API của module ảnh hưởng đồng thời tới tên Java, ranh giới công bố và các quyền phụ thuộc.** Khi đổi `@NamedInterface`, di chuyển kiểu, đổi chữ ký hoặc mở rộng DTO, cần đánh giá cả module cung cấp lẫn module tiêu thụ. **Biên dịch** phát hiện lỗi tương thích ngôn ngữ; **`ApplicationModules.verify()`** phát hiện phụ thuộc vi phạm cấu trúc; **`@ApplicationModuleTest`**, test sự kiện, database và tích hợp phát hiện hồi quy hành vi. Đưa các kiểm tra này vào **CI quality gate** và review phạm vi API công khai để bảo vệ tính độc lập của module qua từng lần refactor.

### Tài liệu tham khảo

- [Spring Modulith Reference — Application Modules và Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith Reference — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
