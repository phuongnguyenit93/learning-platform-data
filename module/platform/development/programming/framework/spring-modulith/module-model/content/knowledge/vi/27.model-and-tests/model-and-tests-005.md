# Test module dùng API module khác

## Vì sao cần kiểm thử qua API công khai?

Trong modular monolith, một module có thể sử dụng chức năng của module khác thông qua API được công bố. Ví dụ, module orders cần tra cứu thông tin sản phẩm từ module catalog trước khi tính giá đơn hàng.

Một bài kiểm thử cho quan hệ này cần trả lời hai câu hỏi:

- Module tiêu thụ có sử dụng API công khai đúng cách và xử lý kết quả đúng không?
- Khi hai module được khởi tạo cùng nhau, Spring có thể tạo các bean cần thiết và luồng tích hợp có hoạt động không?

Spring Modulith cung cấp @ApplicationModuleTest để khởi tạo một module trong phạm vi giới hạn. Bạn có thể chạy module độc lập, chạy cùng các module mà nó phụ thuộc trực tiếp hoặc chạy cùng toàn bộ cây phụ thuộc. Cách này giúp kiểm thử ranh giới module mà không phải khởi động mọi thành phần của ứng dụng cho mỗi bài test.

## Ví dụ quan hệ giữa catalog và orders

Giả sử ứng dụng có hai module:

- **catalog** sở hữu dữ liệu sản phẩm và công bố API tra cứu sản phẩm.
- **orders** sử dụng API đó để tính giá đơn hàng.

Cấu trúc package:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── api
│   │   ├── ProductCatalog.java
│   │   ├── ProductDetails.java
│   │   └── package-info.java
│   └── internal
│       └── DefaultProductCatalog.java
└── orders
    ├── OrderPricing.java
    └── package-info.java
~~~

Package api là named interface của catalog. Module orders được phép sử dụng hợp đồng ở package đó, trong khi cách catalog lưu và truy xuất sản phẩm vẫn nằm trong package internal.

Khai báo named interface:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.catalog.api;
~~~

API công khai:

~~~java
package com.acme.shop.catalog.api;

import java.math.BigDecimal;

public interface ProductCatalog {
    ProductDetails findByCode(String code);
}
~~~

Kiểu dữ liệu trả về cũng thuộc API công khai:

~~~java
package com.acme.shop.catalog.api;

import java.math.BigDecimal;

public record ProductDetails(
    String code,
    BigDecimal unitPrice
) {}
~~~

Module orders khai báo phụ thuộc vào named interface:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Khai báo này thể hiện rằng orders chỉ cần API của catalog. Nó không cần import repository, entity hoặc implementation trong catalog.internal.

## Module tiêu thụ sử dụng API

Lớp nghiệp vụ trong orders inject ProductCatalog:

~~~java
package com.acme.shop.orders;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductDetails;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class OrderPricing {

    private final ProductCatalog products;

    public OrderPricing(ProductCatalog products) {
        this.products = products;
    }

    public PriceQuote quote(String productCode, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        ProductDetails product = products.findByCode(productCode);
        BigDecimal total = product.unitPrice()
            .multiply(BigDecimal.valueOf(quantity));

        return new PriceQuote(product.code(), quantity, total);
    }
}
~~~

Kiểu kết quả thuộc module orders:

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;

public record PriceQuote(
    String productCode,
    int quantity,
    BigDecimal total
) {}
~~~

Implementation thật của ProductCatalog có thể dùng repository và entity nội bộ. Module orders chỉ phụ thuộc vào interface và ProductDetails đã được công bố.

## Khởi tạo test cùng module phụ thuộc trực tiếp

Để kiểm thử luồng orders gọi implementation thật của catalog, đặt test trong package orders và dùng DIRECT_DEPENDENCIES:

~~~java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrderPricingIntegrationTests {

    @Autowired
    OrderPricing pricing;

    @Test
    void calculatesPriceUsingCatalogApi() {
        // Chuẩn bị dữ liệu sản phẩm SKU-001 có đơn giá 20.00
        // bằng fixture hoặc cơ chế tạo dữ liệu test của catalog.

        PriceQuote quote = pricing.quote("SKU-001", 2);

        assertThat(quote.total()).isEqualByComparingTo("40.00");
    }
}
~~~

Test nằm trong package orders nên Spring Modulith xác định orders là module đang được kiểm thử. DIRECT_DEPENDENCIES yêu cầu khởi tạo orders cùng các module mà orders phụ thuộc trực tiếp, trong ví dụ này có catalog.

Spring Modulith giới hạn component scan, auto-configuration và entity scan theo phạm vi module được chọn. Do đó, test có thể khởi động các bean thực của catalog để kiểm tra hợp đồng tích hợp, trong khi những module không liên quan không bị đưa vào context.

Ví dụ trên giả định test đã chuẩn bị dữ liệu SKU-001 trong kho dữ liệu test của catalog. Có thể dùng SQL fixture, builder dữ liệu test hoặc API hỗ trợ test của module sở hữu dữ liệu. Việc chuẩn bị dữ liệu cần tuân theo quyền sở hữu của catalog.

## Chọn bootstrap mode phù hợp

@ApplicationModuleTest hỗ trợ ba mode chính:

| Mode | Phạm vi context | Khi nên dùng |
|---|---|---|
| STANDALONE | Chỉ module đang test | Kiểm thử logic module độc lập hoặc thay thế dependency bên ngoài bằng mock |
| DIRECT_DEPENDENCIES | Module hiện tại và các module phụ thuộc trực tiếp | Kiểm thử tích hợp với API của module mà nó gọi trực tiếp |
| ALL_DEPENDENCIES | Module hiện tại và toàn bộ cây phụ thuộc, gồm cả phụ thuộc gián tiếp | Kiểm thử khi luồng cần các module ở nhiều tầng phụ thuộc |

STANDALONE là giá trị mặc định. Nếu module đang test inject một bean thuộc module khác nhưng context chỉ khởi tạo module hiện tại, quá trình tạo Spring ApplicationContext có thể thất bại vì thiếu bean.

Khi mục tiêu là xác nhận tích hợp thật với API module khác, DIRECT_DEPENDENCIES thường là lựa chọn phù hợp. Chỉ dùng ALL_DEPENDENCIES khi luồng thực sự cần các phụ thuộc gián tiếp; mở rộng context quá nhiều có thể khiến test chậm và khó xác định nguyên nhân lỗi.

## Cô lập module bằng mock API bên ngoài

Không phải mọi bài test của orders đều cần chạy implementation thật của catalog. Khi muốn kiểm tra riêng quy tắc tính giá, có thể giữ STANDALONE và thay ProductCatalog bằng mock.

Với Spring Framework hỗ trợ @MockitoBean:

~~~java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.catalog.api.ProductDetails;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@ApplicationModuleTest
class OrderPricingTests {

    @MockitoBean
    ProductCatalog products;

    @Autowired
    OrderPricing pricing;

    @Test
    void calculatesPriceFromCatalogResult() {
        given(products.findByCode("SKU-001"))
            .willReturn(new ProductDetails(
                "SKU-001",
                new BigDecimal("20.00")
            ));

        PriceQuote quote = pricing.quote("SKU-001", 2);

        assertThat(quote.total()).isEqualByComparingTo("40.00");
    }
}
~~~

Trong bài test này, Spring tạo mock cho ProductCatalog và đưa mock vào ApplicationContext. Test xác nhận orders sử dụng kết quả từ API đúng cách. Implementation thật của catalog không được khởi tạo trong test này.

Mock không chứng minh catalog trả về dữ liệu đúng hoặc truy vấn persistence hoạt động. Những hành vi đó cần được kiểm thử trong module catalog. Khi cần xác nhận hai module phối hợp thật, bổ sung một bài test dùng DIRECT_DEPENDENCIES.

Với dự án dùng phiên bản Spring Boot cũ chưa có @MockitoBean, có thể cần dùng cơ chế mock bean tương ứng của phiên bản đó, chẳng hạn @MockBean.

## API công khai cần được kiểm thử ở cả hai phía

Một API liên module có ít nhất hai trách nhiệm cần kiểm thử:

**Module cung cấp API.** Test trong catalog xác nhận API trả về dữ liệu đúng, xử lý trường hợp không tìm thấy sản phẩm và giữ các quy tắc nghiệp vụ của catalog.

**Module sử dụng API.** Test trong orders xác nhận module gọi đúng API, xử lý kết quả và phản ứng đúng với lỗi hoặc dữ liệu biên mà API có thể trả về.

Ví dụ, catalog nên có bài test riêng cho ProductCatalog. Orders không cần lặp lại toàn bộ test repository của catalog. Bài test tích hợp giữa hai module chỉ cần xác nhận luồng nghiệp vụ quan trọng qua hợp đồng công khai.

Cách phân chia này giúp lỗi được định vị dễ hơn. Nếu test catalog thất bại, vấn đề nằm ở module cung cấp. Nếu test orders với mock thất bại, vấn đề có thể nằm ở cách consumer xử lý hợp đồng. Nếu test DIRECT_DEPENDENCIES thất bại trong khi hai test riêng đều qua, hãy kiểm tra cấu hình bean, wiring hoặc tương tác thực giữa các module.

## Kiểm tra test không vượt qua ranh giới module

Test cũng cần tuân theo API công khai. Không import implementation hoặc repository nội bộ của catalog chỉ để chuẩn bị dữ liệu cho orders.

Một import như sau là dấu hiệu vi phạm ranh giới:

~~~java
import com.acme.shop.catalog.internal.ProductRepository;
~~~

Nếu orders cần dữ liệu test từ catalog, hãy dùng fixture hoặc test support được catalog công bố, hoặc chuẩn bị dữ liệu trong phần test thuộc catalog. Tránh mở package internal chỉ để test thuận tiện.

@ApplicationModuleTest mặc định bật kiểm chứng cấu trúc module tự động qua thuộc tính verifyAutomatically. Ngoài ra, có thể duy trì một bài test kiến trúc riêng:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Bài test này kiểm tra các quy tắc cấu trúc và phụ thuộc module. Nó bổ sung cho test tích hợp, không thay thế việc kiểm tra hành vi nghiệp vụ.

## Khi nào nên dùng module thật và khi nào nên dùng mock?

| Mục tiêu | Cách khởi tạo | Điều được xác nhận |
|---|---|---|
| Kiểm tra logic orders khi API trả về dữ liệu cụ thể | STANDALONE + @MockitoBean | Consumer xử lý hợp đồng đúng |
| Kiểm tra orders phối hợp với catalog thật | DIRECT_DEPENDENCIES | Wiring và luồng tích hợp qua API |
| Kiểm tra luồng phụ thuộc qua nhiều module | ALL_DEPENDENCIES | Hành vi tích hợp trong cây phụ thuộc |
| Kiểm tra implementation catalog | Test đặt trong catalog | API và quy tắc nghiệp vụ của provider |

Nếu một module cần quá nhiều bean từ các module khác để khởi động, đó có thể là dấu hiệu liên kết chặt. Hãy xem xét thu hẹp API, gom trách nhiệm về đúng module sở hữu hoặc chuyển tương tác sang domain event nếu consumer chỉ cần phản ứng khi một sự kiện xảy ra.

Không nên chọn ALL_DEPENDENCIES như giải pháp mặc định cho mọi lỗi khởi tạo context. Trước tiên hãy xác định dependency nào là hợp đồng cần kiểm tra, dependency nào có thể mock và dependency nào cho thấy thiết kế module cần xem xét lại.

## Bài tập vận dụng

Module billing sử dụng API công khai của module customers để lấy thông tin khách hàng và tạo hóa đơn. Module customers có named interface customers::api.

Hãy thiết kế các bài test cho billing:

1. Một bài test STANDALONE mock API khách hàng để kiểm tra cách billing tạo hóa đơn.
2. Một bài test DIRECT_DEPENDENCIES dùng implementation thật của customers để xác nhận luồng tích hợp.
3. Một bài test trong customers để kiểm tra API trả về thông tin đúng và xử lý khách hàng không tồn tại.
4. Một bài kiểm chứng kiến trúc để bảo đảm billing chỉ phụ thuộc vào customers::api.

Kết quả mong đợi: test của billing đặt trong package billing, chỉ import các kiểu công khai từ customers. Bài test dùng mock xác nhận hành vi riêng của billing; bài test dùng DIRECT_DEPENDENCIES xác nhận wiring và tích hợp thật. Test của customers kiểm tra implementation của API tại nơi sở hữu nó.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể đặt test trong đúng package module, chọn STANDALONE hoặc DIRECT_DEPENDENCIES theo mục tiêu, dùng @MockitoBean để cô lập API bên ngoài, kiểm thử luồng tích hợp qua API công khai và giữ test trong ranh giới module.

Tài liệu tham khảo:

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [ApplicationModuleTest API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html)
- [ApplicationModuleTest.BootstrapMode API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.BootstrapMode.html)
- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
