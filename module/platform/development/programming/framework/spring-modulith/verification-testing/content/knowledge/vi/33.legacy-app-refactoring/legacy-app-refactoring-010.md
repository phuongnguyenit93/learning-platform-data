# Giữ hành vi khi di chuyển lớp giữa module

> **Tình huống:** Ứng dụng Spring Boot đang có phép tính giá nằm trong module order. Sau khi tách module pricing, lớp tính giá sẽ được chuyển sang nơi sở hữu đúng nghiệp vụ. Spring Modulith có thể kiểm tra hướng phụ thuộc mới, nhưng **test kiến trúc xanh không có nghĩa hành vi cũ được giữ nguyên**. Bài này hướng dẫn khóa hợp đồng nghiệp vụ trước, chuyển lớp theo từng bước, rồi chứng minh kết quả, Spring bean wiring và tác dụng phụ vẫn tương đương.

## 1. Định nghĩa thế nào là “giữ hành vi”

Một phép di chuyển lớp chỉ an toàn khi các quan sát quan trọng của caller không thay đổi. Đừng chỉ so sánh chữ ký method hoặc việc test compile:

| Quan sát của consumer | Cần giữ gì sau khi chuyển | Cách lấy bằng chứng |
|---|---|---|
| Dữ liệu trả về | Giá trị, độ chính xác decimal, thứ tự/sắp xếp nếu có | Characterization test với input đã khóa |
| Ngoại lệ | Loại exception, điều kiện lỗi, thông điệp nếu có trong hợp đồng | JUnit assertThrows + assert message nếu thuộc API |
| Tác dụng phụ | Bản ghi DB, số lần gọi external service, event phát ra | Integration test hoặc test adapter |
| Transaction | Commit/rollback, thời điểm flush, isolation cần thiết | Test cùng transaction manager và DB |
| Thời điểm | Đồng bộ/bất đồng bộ, retry, idempotency, độ trễ có thể chấp nhận | Event/Scenario test với điều kiện chờ |
| Kết nối runtime | Đúng Spring bean, scope/proxy/qualifier, component scan | @ApplicationModuleTest hoặc context test |
| Hợp đồng dữ liệu | JSON field, HTTP status, message schema, table/column names | API/serialization/schema contract tests |

Để tránh đánh đồng, viết trước một **phiếu bất biến** cho phần đang di chuyển: “Với unitPrice=19.99, quantity=2, discountRate=0.10, tổng tiền trả về 35.98; tỷ lệ làm tròn HALF_UP ở 2 chữ số; cùng điều kiện lỗi khi null; lời gọi hiện chạy đồng bộ”. Đây là acceptance criteria cụ thể cho PR.

## 2. Chọn đường cắt ít rủi ro theo loại lớp

Trước khi chuyển một file, xem nó thuộc loại nào:

1. **Lớp tính toán thuần Java:** ít phụ thuộc và không I/O; dễ chuyển nhất, thích hợp là bước đầu tiên.
2. **Spring @Component/@Service:** phải tính tới constructor injection, @Qualifier, scope, proxy và component scan.
3. **@Transactional service:** di chuyển có thể thay điểm gọi qua Spring proxy hoặc transaction boundary.
4. **JPA @Entity/@Repository:** có rủi ro entity scan, mapping table, identifier, cascade và schema migration.
5. **@EventListener/@ApplicationModuleListener:** có ngữ nghĩa giao dịch, thời điểm nhận event, retry, thứ tự; cần test khác với method đồng bộ.
6. **DTO/event/public class đã xuất ra ngoài:** có thể là hợp đồng qua JSON, reflection hoặc binary compatibility với consumer.

Ưu tiên **tách hợp đồng nhỏ trước, chuyển implementation sau**. Không lấy thành công của một phép di chuyển calculator thuần Java làm bằng chứng rằng di chuyển repository hoặc event listener cũng an toàn.

## 3. Khóa hành vi bằng characterization test trước refactor

Ví dụ trước khi chuyển:

~~~text
com.acme.shop/
  ShopApplication.java
  order/
    OrderManagement.java
    internal/OrderPriceCalculator.java
  inventory/
    ...
~~~

Lớp đang nằm sai owner nghiệp vụ nhưng có phép tính đã được khách hàng sử dụng:

~~~java
// src/main/java/com/acme/shop/order/internal/OrderPriceCalculator.java
package com.acme.shop.order.internal;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;

@Component
public class OrderPriceCalculator {

    public BigDecimal total(
            BigDecimal unitPrice, int quantity, BigDecimal discountRate) {
        return unitPrice.multiply(BigDecimal.valueOf(quantity))
                .multiply(BigDecimal.ONE.subtract(discountRate))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

OrderManagement là đầu vào của caller:

~~~java
// src/main/java/com/acme/shop/order/OrderManagement.java (trước chuyển)
package com.acme.shop.order;

import java.math.BigDecimal;
import com.acme.shop.order.internal.OrderPriceCalculator;
import org.springframework.stereotype.Service;

@Service
public class OrderManagement {

    private final OrderPriceCalculator calculator;

    public OrderManagement(OrderPriceCalculator calculator) {
        this.calculator = calculator;
    }

    public BigDecimal previewTotal(
            BigDecimal unitPrice, int quantity, BigDecimal discountRate) {
        return calculator.total(unitPrice, quantity, discountRate);
    }
}
~~~

Thêm characterization test **đi qua OrderManagement**, vì đây là điểm giao tiếp cần bảo vệ sau refactor:

~~~java
// src/test/java/com/acme/shop/order/OrderPricingContractTest.java
package com.acme.shop.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
        mode = DIRECT_DEPENDENCIES,
        verifyAutomatically = false)
class OrderPricingContractTest {

    @Autowired OrderManagement orders;

    @ParameterizedTest
    @CsvSource({
        "19.99, 2, 0.10, 35.98",
        "0.05, 3, 0.15, 0.13",
        "9.995, 1, 0.00, 10.00",
        "2.50, 3, 1.00, 0.00"
    })
    void returnsSameAmount(
            String unitPrice, int quantity, String discount, String expected) {
        var actual = orders.previewTotal(
                new BigDecimal(unitPrice),
                quantity,
                new BigDecimal(discount));
        assertEquals(new BigDecimal(expected), actual);
    }

    @Test
    void nullPriceStillThrows() {
        assertThrows(NullPointerException.class,
                () -> orders.previewTotal(null, 1, BigDecimal.ZERO));
    }
}
~~~

Ở ví dụ legacy đang có vi phạm khác, tạm dùng verifyAutomatically=false để test hành vi không bị thất bại bởi quy tắc toàn ứng dụng **chưa được xử lý**; giữ test kiến trúc riêng chạy trong CI. Khi module sạch, trả về verifyAutomatically=true (mặc định). DIRECT_DEPENDENCIES chạy order và các module order phụ thuộc trực tiếp; phù hợp trước và sau khi order phụ thuộc pricing.

Chạy test trước khi sửa và lưu kết quả PASS làm mốc. Nếu thực tế hệ thống cho phép quantity=0, quantity âm hay discount ngoài [0,1], phải thêm các tình huống đó theo đúng hành vi **đang tồn tại**; không lén thay validation hoặc rounding trong cùng PR di chuyển.

## 4. Thiết kế API công khai trước khi chuyển implementation

Mục tiêu mới:

~~~mermaid
flowchart LR
    Buyer["Caller / REST"] --> Order["order: OrderManagement"]
    Order --> PricingAPI["pricing: PricingOperations (public API)"]
    PricingAPI --> PricingImpl["pricing.internal: DefaultPricingOperations"]
~~~

Trong Spring Modulith, package gốc của pricing là API mặc định; pricing.internal là chi tiết triển khai. Định nghĩa interface ở biên, giữ hợp đồng nhỏ:

~~~java
// src/main/java/com/acme/shop/pricing/PricingOperations.java
package com.acme.shop.pricing;

import java.math.BigDecimal;

public interface PricingOperations {

    BigDecimal total(
            BigDecimal unitPrice, int quantity, BigDecimal discountRate);
}
~~~

Giữ chữ ký tương ứng với yêu cầu hiện tại giúp tránh đổi đồng thời request DTO, format tiền và logic tính giá. Chỉ thêm DTO chuyên biệt khi có lý do kiến trúc cụ thể và có characterization test bao phủ chuyển đổi dữ liệu. Interface của module **không** nên trả về order.internal.OrderEntity hoặc pricing.internal.JpaPriceRow vì như vậy tái tạo lỗi phụ thuộc vào chi tiết nội bộ.

## 5. Chuyển implementation và cập nhật constructor injection

Tạo implementation trong module mới, giữ nguyên biểu thức, RoundingMode và thời điểm tính:

~~~java
// src/main/java/com/acme/shop/pricing/internal/DefaultPricingOperations.java
package com.acme.shop.pricing.internal;

import java.math.BigDecimal;
import java.math.RoundingMode;
import com.acme.shop.pricing.PricingOperations;
import org.springframework.stereotype.Component;

@Component
public class DefaultPricingOperations implements PricingOperations {

    @Override
    public BigDecimal total(
            BigDecimal unitPrice, int quantity, BigDecimal discountRate) {
        return unitPrice.multiply(BigDecimal.valueOf(quantity))
                .multiply(BigDecimal.ONE.subtract(discountRate))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

OrderManagement sau di chuyển chỉ tham chiếu API của pricing:

~~~java
// src/main/java/com/acme/shop/order/OrderManagement.java (sau chuyển)
package com.acme.shop.order;

import java.math.BigDecimal;
import com.acme.shop.pricing.PricingOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderManagement {

    private final PricingOperations pricing;

    public OrderManagement(PricingOperations pricing) {
        this.pricing = pricing;
    }

    public BigDecimal previewTotal(
            BigDecimal unitPrice, int quantity, BigDecimal discountRate) {
        return pricing.total(unitPrice, quantity, discountRate);
    }
}
~~~

Sau khi tất cả caller đã chuyển, xóa bean OrderPriceCalculator cũ; không để hai bean cùng đảm nhận một chức năng rồi dựa vào @Primary để test đi qua bean mới một cách tình cờ. Cũng không dùng component-scan ngoài package ứng dụng để “cứu” một bean bị thiếu: sửa package ownership hoặc cấu hình scan đúng với thiết kế mới.

Nếu pricing cần khai báo quyền phụ thuộc rõ ràng, xem lại hướng order → pricing. Ví dụ chỉ order được gọi pricing thì package-info.java thuộc **order** phải phản ánh dependency được cho phép; khai báo trong pricing sẽ kiểm soát dependency **pricing → module khác**, không thay thế khai báo của order.

~~~java
// src/main/java/com/acme/shop/order/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {"pricing"}
)
package com.acme.shop.order;
~~~

Nếu order còn phụ thuộc hợp lệ vào inventory, liệt kê cả inventory trong allowedDependencies; thay đổi danh sách phải theo thực tế dependency đã được chấp thuận. Cấu trúc cuối mong đợi là order → pricing, không có vòng ngược pricing → order.

## 6. Chạy lại architecture verification để chứng minh ranh giới mới

Sau khi sửa code, bổ sung một bài test cho kiến trúc **đích**:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithBoundaryTest {

    @Test
    void verifyModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nếu ứng dụng đã sạch vi phạm, test trên phải PASS. Nếu còn nợ kiến trúc được duyệt từ phần legacy khác, kiểm tra bằng legacy gate của bài baseline thay vì bật verify() nghiêm ngặt trong pipeline rồi kỳ vọng toàn bộ ứng dụng xanh. Điều bắt buộc cho phép chuyển lớp này là **không phát sinh vi phạm mới**, đồng thời dependency order → pricing được phép và pricing không truy cập order.internal.

Một lỗi điển hình là chuyển OrderPriceCalculator sang pricing.internal rồi để OrderManagement import trực tiếp DefaultPricingOperations. Ứng dụng vẫn compile và vẫn cho ra 35.98, nhưng verify() báo truy cập package nội bộ. Sửa bằng cách inject PricingOperations tại package gốc pricing. Điều này cho thấy hai bộ bằng chứng đo hai thứ khác nhau: **behavior test** giữ kết quả, **architecture test** giữ ranh giới.

## 7. Xác minh Spring bean wiring và module bootstrap

Không bỏ qua kiểm thử runtime chỉ vì Java compile. Lớp mới có thể không được scan, có thể bị tạo trùng bean, hoặc một cấu hình @Qualifier có thể tiếp tục trỏ tới tên bean cũ. @ApplicationModuleTest từ mục 3 sẽ tạo Spring context cho order cùng dependency trực tiếp:

~~~java
// Một test chuyên biệt để biết đã inject đúng implementation mới
package com.acme.shop.order;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES;

import com.acme.shop.pricing.PricingOperations;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
        mode = DIRECT_DEPENDENCIES,
        verifyAutomatically = false)
class PricingWiringTest {

    @Autowired PricingOperations pricing;

    @Test
    void publicPricingApiIsResolvable() {
        assertNotNull(pricing);
    }
}
~~~

Một bean PricingOperations được resolve chỉ khẳng định wiring tồn tại; OrderPricingContractTest vẫn cần chạy để bảo vệ phép tính thực tế. Nếu test STANDALONE thất bại vì thiếu PricingOperations, đó là tín hiệu dependency trực tiếp đã xuất hiện. Có thể dùng DIRECT_DEPENDENCIES để khởi động module pricing thật, hoặc mock PricingOperations nếu muốn test độc lập hoàn toàn hành vi order; không mở ALL_DEPENDENCIES theo quán tính nếu không cần.

## 8. Với class có side effect, khóa transaction, dữ liệu và event

Ví dụ calculator là pure function, nhưng trong thực tế lớp cần di chuyển có thể vừa tính vừa ghi DB hoặc phát event. Trước khi đổi owner module, lập ma trận rủi ro:

| Thành phần đi kèm | Thất bại thường gặp sau khi move | Ca kiểm chứng tối thiểu |
|---|---|---|
| @Transactional | Self-invocation không đi qua proxy; chuyển method transactional sang private; rollback khác | Gây exception sau bước ghi, xác nhận DB rollback |
| JPA @Entity | Entity scan bỏ sót package mới; default table naming khác; lazy relation lỗi | Boot context, đọc/ghi entity, xác nhận schema/table và cascade |
| @Repository | Không được tạo bean, hoặc dùng sai datasource/entity manager | Integration test gọi method trên DB kiểm thử |
| Domain event | Đổi synchronous call sang async listener làm thay đổi thời điểm cập nhật | Kiểm tra event payload, giao dịch, thứ tự và eventual consistency |
| @Cacheable/@Async/@Scheduled | Thay bean name hoặc proxy, job chạy hai lần | Kiểm tra số lần gọi, thread, cache key/TTL hoặc job registration |
| Serialized DTO/event | Đổi tên package/class làm consumer không giải mã được | Golden JSON/schema contract; compatibility test qua serializer |

Với service transactional, ví dụ đang có OrderManagement.placeOrder() mở transaction rồi tính giá và ghi OrderEntity. Chuyển **phần tính toán** sang pricing là an toàn hơn chuyển cả phương thức placeOrder() sang pricing: transaction owner vẫn là order, repository không bị kéo qua module. Nếu muốn di chuyển transaction boundary thật, cần nêu rõ owner mới và test rollback; Spring proxy chỉ áp dụng khi lời gọi đi qua bean proxy thích hợp.

Không mặc nhiên chuyển lời gọi đồng bộ thành @ApplicationModuleListener để giảm coupling. Listener kiểu này tích hợp xử lý event theo ngữ nghĩa riêng; consumer có thể không thấy kết quả ngay trong cùng transaction. Nếu nghiệp vụ đòi “gửi đơn hàng xong là giá đã tính và DB đã cập nhật”, đổi sang async là thay đổi behavior cần một thiết kế/migration riêng, kể cả verify() đã xanh.

## 9. Rollout từng bước và kiểm soát tương thích

Một chuỗi commit/PR giúp lỗi dễ khoanh vùng:

1. **Commit 1 – Characterize:** Thêm OrderPricingContractTest, chụp bằng chứng PASS trước khi đụng code.
2. **Commit 2 – Expose API:** Thêm PricingOperations ở pricing; giữ caller vẫn dùng calculator cũ cho đến khi cấu hình mới sẵn sàng.
3. **Commit 3 – Move implementation:** Chuyển phép tính nguyên văn sang pricing.internal.DefaultPricingOperations; đổi OrderManagement sang inject interface.
4. **Commit 4 – Remove old path:** Xóa OrderPriceCalculator, xử lý import và cấu hình bean cũ; chạy regression tests và architecture verification.
5. **Commit 5 – Clean up:** Xóa ngoại lệ kiến trúc đã hết hiệu lực; cập nhật tài liệu hợp đồng và ownership của pricing.

Từng commit có thể không hoàn toàn deploy được nếu tạm có hai implementation; điều kiện merge/deploy là **trạng thái cuối được kiểm chứng**. Với repository nhiều ứng dụng hoặc consumer deploy độc lập, cần làm rõ binary/source compatibility: đổi package của public class có thể làm hỏng client đang compile theo FQCN cũ. Khi đó giữ một adapter công khai có lịch deprecate hoặc phát hành API phiên bản mới, và kiểm chứng vòng đời hỗ trợ consumer.

Để tránh hai implementation trả kết quả khác nhau, không copy công thức sang nơi mới rồi sửa một bên; di chuyển đúng một đường thực thi. Chỉ đặt adapter mỏng ở nơi cũ nếu có consumer ngoài phạm vi cần thời gian chuyển đổi, kèm test cho cả adapter và API mới.

## 10. Bài tập kiểm chứng và tiêu chí hoàn thành

**Đề bài:** OrderManagement đang dùng trực tiếp một calculator trong order.internal. Nhóm muốn chuyển calculator sang pricing, giữ chính xác phép tính hiện tại và cấm order gọi pricing.internal.

Thực hiện theo thứ tự:

1. Viết bảng ít nhất 6 input/output hiện hữu, gồm rounding, quantity biên và các lỗi đầu vào đang được caller nhận.
2. Đặt JUnit characterization test tại điểm gọi công khai OrderManagement; chạy PASS trước khi di chuyển.
3. Thêm PricingOperations ở root package pricing; di chuyển implementation sang pricing.internal; xóa implementation cũ sau khi caller đã cập nhật.
4. Chạy lại **nguyên test**, không sửa expected value chỉ để xanh.
5. Chạy @ApplicationModuleTest(mode = DIRECT_DEPENDENCIES) để phát hiện sai bean wiring.
6. Chạy kiểm chứng Spring Modulith; thử import DefaultPricingOperations từ order để xác nhận rule cấm internal thực sự phát hiện được.
7. Nếu có DB/event, thêm bằng chứng rollback/payload/thời điểm xử lý trước và sau.

**Kết quả đạt:** Tất cả case hành vi trước và sau khớp; Spring context chỉ dùng bean pricing mới; không có truy cập internal trái phép; không có phụ thuộc vòng; bản diff xác định được đường caller đã chuyển. Nếu chỉ có verify() PASS mà thiếu characterization test, bài chưa đạt yêu cầu “giữ hành vi”.

**Tài liệu tham khảo:** [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html), [Spring Modulith – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html), [ApplicationModuleTest API và BootstrapMode](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html), [Spring Framework – Transaction declarative semantics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html).
