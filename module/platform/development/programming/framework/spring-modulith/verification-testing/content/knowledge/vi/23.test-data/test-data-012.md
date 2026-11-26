# Giảm fixture dư thừa làm test khó đọc

> **Chương:** Test data  
> **Phạm vi:** `SPRING_MODULITH_VERIFICATION_TESTING` — rèn kỹ năng kiểm chứng ranh giới kiến trúc Spring Modulith bằng `ApplicationModules` và quy tắc phụ thuộc module; thực hành `@ApplicationModuleTest`, event, database, integration tests và CI quality gate để ngăn phụ thuộc sai, hồi quy.

## 1. Nhìn một test và biết ngay điều gì đang được chứng minh

**Yêu cầu nghiệp vụ:** Nếu không đủ hàng, `orders` không được lưu đơn và không được phát `OrderPlaced`.

Một test có thể PASS nhưng vẫn khó đọc vì `Given` chứa rất nhiều thứ không ảnh hưởng kết quả:

```java
// Anti-pattern: pseudocode minh họa cách setup quá mức;
// các helper ở đây không phải public API của ví dụ bên dưới.
@Test
void outOfStockDoesNotPlaceOrder() {
    var customer = aCustomer()
            .withContactEmail("buyer@example.test")
            .withThreeAddresses()
            .withLoyaltyTier("GOLD")
            .build();
    var product = aProduct()
            .withBrand("Sample Brand")
            .withNineImages()
            .withSeoMetadata()
            .build();
    var campaign = aCampaign().withTenRules().build();
    var payment = aPaymentMethod().withBillingProfile().build();
    var shipment = aShippingPlan().withThreeCarriers().build();

    seed(customer, product, campaign, payment, shipment);
    seedManyUnrelatedOrders(20);
    setStock(product.sku(), 0);

    assertThrows(OutOfStockException.class,
            () -> placeOrder(product.sku(), 2));
    assertEquals(0, orderCountFor(product.sku()));
}
```

Để hiểu assertion cuối, người đọc phải lướt qua customer, shipping, campaign, payment và 20 orders. Chưa rõ **thiếu hàng** là nguyên nhân từ chối, hay một fixture phụ đã khiến hành động không chạy; cũng chưa có assertion rằng event không phát.

Phiên bản gọn hơn có thể nói đúng hợp đồng trong một màn hình:

```text
Given: StockAvailability báo hết hàng cho SKU-001
When:  đặt 2 đơn vị SKU-001, orderId = ID của scenario
Then:  OUT_OF_STOCK; không gọi writer; không publish OrderPlaced
```

**Giảm fixture dư thừa không phải “càng ít dòng càng tốt”.** Mục tiêu là mỗi dữ liệu trong `Given` phải có lý do để tồn tại và liên hệ trực tiếp với hành động hoặc assertion. Một test có ba rows đối chứng có thể **tốt hơn** test chỉ một row nếu ba rows mới bắt được lỗi query thiếu filter.

## 2. Xác định “dữ liệu tối thiểu nhưng đủ phân biệt đúng–sai”

Trước khi viết factory, lập bảng vai trò cho dữ liệu cần tạo:

| Dữ liệu | Có phục vụ test hết hàng? | Quyết định |
| --- | --- | --- |
| `orderId` | Có: liên kết lệnh và hệ quả quan sát | Giữ, cấp một lần |
| `sku` và `quantity` | Có: input của stock check | Giữ |
| Kết quả `StockAvailability=false` | Có: nguyên nhân chính của nhánh fail | Giữ, làm rõ bằng tên |
| Writer nhận lệnh lưu? | Có: kiểm không có side effect | Local spy hoặc mock |
| Event publisher có publish? | Có: kiểm không có event | Local spy hoặc `PublishedEvents` |
| Customer address/loyalty | Không, nếu service không dùng trong đường này | Bỏ |
| Payment method/campaign | Không, nếu không được gọi | Bỏ |
| 20 orders khác trong database | Không, nếu test chỉ cần kiểm writer không gọi | Bỏ |
| Spring/DB container | Không cần cho unit test điều kiện hết hàng | Để dành integration test |

### 2.1. Bốn phép hỏi cho mỗi dòng setup

1. **Nguyên nhân:** Nếu xóa dòng này, branch `When` có thay đổi ý nghĩa không?
2. **Quan sát:** Có assertion nào sẽ phát hiện việc dữ liệu này sai không?
3. **Quyền sở hữu:** Dữ liệu thuộc scenario này hay đang kéo state từ test khác?
4. **Tầng:** Đang kiểm business decision, wiring của `@ApplicationModuleTest` hay persistence/integration?

Nếu không trả lời được câu hỏi nào cho một fixture, nhiều khả năng đó là dữ liệu không cần thiết hoặc test đang thiếu assertion.

### 2.2. “Tối thiểu” có hai chiều

| Tối thiểu về số lượng | Tối thiểu về ý nghĩa |
| --- | --- |
| Không tạo object/row không cần | Giữ dữ liệu **đối chứng** có khả năng phát hiện implementation sai |
| Không dựng cả graph customer/payment cho test stock | Giữ stock=false và kiểm không save/event |
| Không seed 30 orders cho query filtering | Vẫn cần ít nhất một row được chọn và các rows phải bị loại |
| Không khởi động broker cho unit event mapper | Với listener retry thật, phải dùng broker/database cần thiết |

Đừng biến một test dễ đọc thành một test **không thể FAIL trước bug**. Định nghĩa một “đối thủ” cụ thể: *nếu developer quên kiểm tồn kho / bỏ WHERE status / publish event khi reject thì test có đỏ không?*

## 3. Mô hình Java nhỏ để test không cần cả hệ sinh thái fixture

Ví dụ thống nhất: `orders` là module chịu trách nhiệm đặt đơn; nó hỏi tồn kho qua public API của `inventory`, lưu order bằng port của chính module và publish `OrderPlaced`. Các file được trình bày tách theo package, không cần entity graph hay database để test quyết định “hết hàng”.

### 3.1. Contract của `inventory`

`src/main/java/com/example/shop/inventory/StockAvailability.java`:

```java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean hasStock(String sku, int quantity);
}
```

Ở integration runtime, module `inventory` phải có implementation cho interface này. Unit/module test có thể cung cấp stub qua public API, **không** import `inventory.internal` để seed dữ liệu.

### 3.2. Command và event của `orders`

`src/main/java/com/example/shop/orders/PlaceOrderCommand.java`:

```java
package com.example.shop.orders;

import java.util.UUID;

public record PlaceOrderCommand(
        UUID orderId, String sku, int quantity
) {
    public PlaceOrderCommand {
        if (orderId == null || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_INPUT");
        }
    }
}
```

`src/main/java/com/example/shop/orders/OrderPlaced.java`:

```java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId, String sku, int quantity) {}
```

Event có ba fields cần thiết cho use case minh họa; không tự đưa address, payment hoặc inventory internal model vào chỉ để fixture “thật hơn”.

### 3.3. Port và service của `orders`

`src/main/java/com/example/shop/orders/OrderWriter.java`:

```java
package com.example.shop.orders;

import java.util.UUID;

interface OrderWriter {
    void save(UUID orderId, String sku, int quantity);
}
```

`src/main/java/com/example/shop/orders/OrderPlacementService.java`:

```java
package com.example.shop.orders;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import com.example.shop.inventory.StockAvailability;

@Service
public class OrderPlacementService {

    private final StockAvailability stock;
    private final OrderWriter writer;
    private final ApplicationEventPublisher events;

    public OrderPlacementService(
            StockAvailability stock,
            OrderWriter writer,
            ApplicationEventPublisher events) {
        this.stock = stock;
        this.writer = writer;
        this.events = events;
    }

    public OrderPlaced place(PlaceOrderCommand command) {
        if (!stock.hasStock(command.sku(), command.quantity())) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        writer.save(
                command.orderId(), command.sku(), command.quantity());
        OrderPlaced event = new OrderPlaced(
                command.orderId(), command.sku(), command.quantity());
        events.publishEvent(event);
        return event;
    }
}
```

Đây là service dạy học để cô lập **điều kiện, write và event**. Nó chưa cam kết atomicity giữa DB và event, idempotency hay transaction/retry. Các rủi ro đó cần integration test riêng, không cần lôi vào fixture của **unit test hết hàng**.

## 4. JUnit: viết `Given` ngắn mà vẫn assert đủ hành vi

Một unit test thuần không cần `@SpringBootTest` hoặc Testcontainers nếu collaborators của service được tạo ngay trong method.

`src/test/java/com/example/shop/orders/OrderPlacementServiceTest.java`:

```java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import com.example.shop.inventory.StockAvailability;

class OrderPlacementServiceTest {

    @Test
    void outOfStockDoesNotWriteOrPublish() {
        UUID orderId = UUID.randomUUID();
        PlaceOrderCommand command =
                new PlaceOrderCommand(orderId, "SKU-001", 2);

        StockAvailability noStock = (sku, quantity) -> false;
        List<UUID> savedIds = new ArrayList<>();
        List<Object> published = new ArrayList<>();
        OrderWriter writer = (id, sku, quantity) -> savedIds.add(id);
        ApplicationEventPublisher events = published::add;
        OrderPlacementService service =
                new OrderPlacementService(noStock, writer, events);

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> service.place(command));

        assertEquals("OUT_OF_STOCK", failure.getMessage());
        assertTrue(savedIds.isEmpty(), "no order must be written");
        assertTrue(published.isEmpty(), "no event must be published");
    }

    @Test
    void availableStockWritesAndPublishesForThisOrder() {
        UUID orderId = UUID.randomUUID();
        PlaceOrderCommand command =
                new PlaceOrderCommand(orderId, "SKU-001", 2);

        StockAvailability hasStock = (sku, quantity) -> true;
        List<UUID> savedIds = new ArrayList<>();
        List<Object> published = new ArrayList<>();
        OrderWriter writer = (id, sku, quantity) -> savedIds.add(id);
        OrderPlacementService service = new OrderPlacementService(
                hasStock, writer, published::add);

        OrderPlaced returned = service.place(command);

        assertEquals(orderId, returned.orderId());
        assertEquals("SKU-001", returned.sku());
        assertEquals(2, returned.quantity());
        assertEquals(List.of(orderId), savedIds);
        assertEquals(1, published.size());
        OrderPlaced event = assertInstanceOf(
                OrderPlaced.class, published.get(0));
        assertEquals(orderId, event.orderId());
    }
}
```

**Điều đã được tối giản:** Không cần customer entity, shipping graph, payment gateway, SQL seed hoặc application context. `savedIds` và `published` là recorder **local trong từng method**, nên không cần reset toàn cục và không rò sang test khác.

**Điều vẫn được giữ:** Một command cụ thể, kết quả stock cần thiết và assertions cho cả hai side effects. Nếu refactor production bỏ kiểm tồn kho, test `outOfStockDoesNotWriteOrPublish` sẽ FAIL. Nếu quên publish ở nhánh thành công, test thứ hai sẽ FAIL.

### 4.1. Khi nào cần Mockito?

Mockito có giá trị nếu bạn phải kiểm **chính xác tương tác** với một collaborator phức tạp (ví dụ repository nhận aggregate với nhiều fields), hoặc muốn `verifyNoInteractions(...)`. Nhưng dùng bốn `@Mock` không cần thiết chỉ vì mọi unit test “phải có mock”.

Trong ví dụ, hai `List` local thể hiện rõ “không ghi/không phát”. Nếu nâng service để truyền một aggregate phức tạp, một `ArgumentCaptor` có thể sáng sủa hơn tự định nghĩa recording fake nhiều dòng. Chọn cách nào giúp người đọc biết **điều gì quan trọng** trong vòng vài giây, không chọn theo số dòng ngắn nhất.

## 5. Dùng factory khi nó giảm lặp **mà không giấu biến quan trọng**

Khi hàng chục tests lặp lại constructor `PlaceOrderCommand`, một helper nhỏ có thể đáng giá. Nhưng builder kiểu “mọi thứ tùy chọn” đôi khi chỉ chuyển một fixture dài sang một file dài hơn, khiến tests không còn nhìn thấy các giả định mặc định.

### 5.1. Factory nhỏ với default được đặt tên

`src/test/java/com/example/shop/orders/OrderCommands.java`:

```java
package com.example.shop.orders;

import java.util.UUID;

final class OrderCommands {

    private OrderCommands() {}

    static PlaceOrderCommand standard() {
        return new PlaceOrderCommand(
                UUID.randomUUID(), "SKU-001", 2);
    }

    static PlaceOrderCommand withQuantity(int quantity) {
        return new PlaceOrderCommand(
                UUID.randomUUID(), "SKU-001", quantity);
    }
}
```

Điểm quan trọng: `standard()` có tên thể hiện dữ liệu hợp lệ; `withQuantity(...)` chỉ mở một biến mà tests thực sự thay đổi. Mỗi invocation tạo **command mới có ID riêng**, không dùng một `static mutable Order`. Vì `PlaceOrderCommand` là record có validation, helper không tạo tình trạng bất hợp lệ một cách im lặng.

Ví dụ tập trung vào nhánh theo số lượng hàng:

```java
@Test
void stockCheckSeesRequestedQuantity() {
    PlaceOrderCommand command = OrderCommands.withQuantity(5);
    // Tạo một stock fake theo scope method và kiểm quantity=5
    // khi gọi OrderPlacementService.place(command).
}
```

Đây là fragment mô tả điểm thay đổi chính, không phải một test behavior hoàn chỉnh. Khi dùng factory trong test thật, vẫn cần `When` và `Then` kiểm service. Nếu một test chỉ viết `OrderCommands.standard()` mà không dùng output, factory chẳng giúp chứng minh gì.

### 5.2. Với một test duy nhất, constructor trực tiếp có thể rõ hơn

```java
PlaceOrderCommand command = new PlaceOrderCommand(
        UUID.randomUUID(), "SKU-BACKORDER", 4);
```

Không cần tạo builder `anOrder().withSku(...).withQuantity(...).build()` chỉ để bọc một constructor ba tham số. Một helper tốt cần được **nhiều test tái dùng với cùng một ý nghĩa** hoặc che đúng phần setup rườm rà nhưng ổn định (ví dụ dữ liệu hợp lệ của một aggregate nhiều invariant).

### 5.3. Object Mother, builder và `@BeforeEach`: chọn theo tín hiệu

| Công cụ | Nên dùng | Dấu hiệu dùng quá mức |
| --- | --- | --- |
| Named factory như `standard()` | Nhiều tests cùng một baseline hợp lệ | Đặt tên chung chung `createDefault()`, mặc định không rõ |
| Builder với `with...` | Nhiều fields bắt buộc, mỗi test đổi vài fields khác nhau | Builder có hàng chục cờ, tạo trạng thái vô nghĩa |
| Object Mother | Những biến thể nghiệp vụ lặp: `paidOrder()`, `cancelledOrder()` | Mother tạo toàn bộ entity graph cho mọi test |
| `@BeforeEach` | Hạ tầng nhẹ cần mới mỗi method | Chuẩn bị 8 objects mà chỉ 1/3 tests dùng |
| Parameterized test | Cùng hành vi, nhiều giá trị biên có nghĩa | Gộp scenarios khác nguyên nhân vào một test tên mơ hồ |
| Test fixture file JSON/SQL | Cần payload/schema lịch sử chính xác | Mỗi test load một snapshot đồ sộ không dùng |

Không sửa API production để chứa `@Builder` hoặc constructor chỉ phục vụ test khi một test-only factory là đủ. Ngược lại, nếu setup nhiều dòng vì domain thật sự có invariant phức tạp, cần cân nhắc liệu public domain API đã cung cấp cách tạo aggregate hợp lệ và dễ dùng chưa.

### 5.4. Negative case không nhất thiết qua happy-path builder

Constructor `PlaceOrderCommand` từ chối quantity không dương. Để kiểm rule đó, tạo input sai **ngay tại ranh giới validation**:

```java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderCommandValidationTest {

    @ParameterizedTest
    @ValueSource(ints = {0, -1})
    void rejectsNonPositiveQuantity(int invalidQuantity) {
        assertThrows(IllegalArgumentException.class,
                () -> new PlaceOrderCommand(
                        UUID.randomUUID(), "SKU-001", invalidQuantity));
    }
}
```

Không tạo một builder “unsafe” rồi dùng reflection để xuyên qua record validation. Nếu cần kiểm cách database xử lý quantity 0 do dữ liệu legacy, đó là một **persistence/legacy scenario riêng** với SQL fixture thích hợp.

## 6. Database fixture: bớt rows, nhưng giữ đủ **negative controls**

Một anti-pattern khác là seed hàng chục orders/customer/payment records để kiểm một query đơn giản. Với câu hỏi “liệt kê đơn `PLACED` của khách A”, một bộ dữ liệu **ba rows** thường đủ để phát hiện cả hai loại lỗi: bỏ filter trạng thái và bỏ filter khách hàng.

### 6.1. Production query và schema minh họa

Giả sử migration thật của module `orders` có bảng:

```sql
CREATE TABLE order_projection (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('PLACED', 'CANCELLED'))
);
```

`src/main/java/com/example/shop/orders/OrderReadService.java`:

```java
package com.example.shop.orders;

import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {

    private final JdbcTemplate jdbc;

    public OrderReadService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<UUID> placedOrderIdsFor(UUID customerId) {
        return jdbc.query(
            "SELECT id FROM order_projection "
                + "WHERE customer_id = ? AND status = 'PLACED' "
                + "ORDER BY id",
            (rs, rowNum) -> rs.getObject("id", UUID.class),
            customerId
        );
    }
}
```

Ví dụ cố ý không cần `Customer` entity hoặc payment/shipping tables. Trong domain thật, chọn query/service và dữ liệu hợp lệ theo migrations của chính dự án; đừng tạo bảng test khác schema production chỉ để minh họa.

### 6.2. Ba rows có ba vai trò khác nhau

| Row | Customer | Status | Vì sao cần? |
| --- | --- | --- | --- |
| `A1` | `CUSTOMER_A` | `PLACED` | **Positive control**: phải được trả về |
| `A2` | `CUSTOMER_A` | `CANCELLED` | **Negative control** cho filter status |
| `B1` | `CUSTOMER_B` | `PLACED` | **Negative control** cho filter customer |

Nếu chỉ có một row `A1`, query sai `SELECT id FROM order_projection` hoặc query quên `status` đều có thể PASS. Không cần thêm 30 rows vì chúng không mang một vai trò đối chứng mới.

### 6.3. Spring/JDBC integration test với data đúng scope

`src/test/java/com/example/shop/orders/OrderReadServiceTest.java`:

```java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class OrderReadServiceTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    OrderReadService reader;

    private void row(UUID id, UUID customerId, String status) {
        jdbc.update(
            "INSERT INTO order_projection "
                + "(id, customer_id, status) VALUES (?, ?, ?)",
            id, customerId, status);
    }

    @Test
    void filtersBothStatusAndCustomer() {
        UUID customerA = UUID.randomUUID();
        UUID customerB = UUID.randomUUID();
        UUID placedA = UUID.randomUUID();
        UUID cancelledA = UUID.randomUUID();
        UUID placedB = UUID.randomUUID();

        try {
            row(placedA, customerA, "PLACED");
            row(cancelledA, customerA, "CANCELLED");
            row(placedB, customerB, "PLACED");

            List<UUID> actual = reader.placedOrderIdsFor(customerA);

            assertEquals(List.of(placedA), actual);
        } finally {
            jdbc.update(
                "DELETE FROM order_projection WHERE id IN (?, ?, ?)",
                placedA, cancelledA, placedB);
        }
    }
}
```

**Giới hạn của ví dụ:** Project phải cấu hình `DataSource`/JDBC, database driver và migration tạo `order_projection`; các dependencies của full `@SpringBootTest` phải thỏa mãn. Test không cần SQL “seed cả thế giới”. `finally` giúp cleanup đúng ba IDs, nhưng khi database bị mất kết nối hoặc process bị dừng, môi trường test vẫn cần cơ chế tái khởi tạo. Tránh dùng một bảng/schema production thực làm test target.

### 6.4. Kiểm fixture không bị lẫn nghĩa

Khi refactor bỏ hàng chục rows, giữ ít nhất một negative control cho **mỗi nhánh WHERE quan trọng**. Đổi code query thử thành chỉ `WHERE status = 'PLACED'`; row `B1` phải làm test FAIL. Đổi thành chỉ `WHERE customer_id = ?`; row `A2` phải làm test FAIL. Hai phép thử này giúp bảo đảm việc tối giản **không làm test trở nên dễ qua**.

## 7. `@ApplicationModuleTest`: giữ đủ wiring, bỏ business data không liên quan

Khi chuyển từ unit test sang Spring Modulith module test, setup thường phình ra vì người viết cố tạo cả database customer/product/inventory và payment để một service có thể boot. Với test **hợp đồng `OrderPlaced`**, chỉ cần:

1. Bean `OrderPlacementService` thật.
2. Một `StockAvailability` có kết quả được kiểm soát.
3. Một `OrderWriter` phù hợp mục tiêu, có thể no-op vì **không** kiểm persistence ở test này.
4. Event được Spring thu thập bằng `PublishedEvents`.

### 7.1. Test config gọn và không giữ state giữa scenarios

`src/test/java/com/example/shop/orders/OrderModuleEventsTest.java`:

```java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import com.example.shop.inventory.StockAvailability;

@ApplicationModuleTest
@Import(OrderModuleEventsTest.Collaborators.class)
class OrderModuleEventsTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class Collaborators {

        @Bean
        @Primary
        StockAvailability stockAvailable() {
            return (sku, quantity) -> true;
        }

        @Bean
        @Primary
        OrderWriter orderWriter() {
            // No-op chỉ vì test này KHÔNG kiểm persistence.
            return (id, sku, quantity) -> {};
        }
    }

    @Autowired
    OrderPlacementService service;

    @Test
    void publishesOrderIdentityWithoutUnrelatedFixture(
            PublishedEvents published) {
        UUID orderId = UUID.randomUUID();
        PlaceOrderCommand command =
                new PlaceOrderCommand(orderId, "SKU-001", 2);

        service.place(command);

        assertThat(published.ofType(OrderPlaced.class))
                .anySatisfy(event -> {
                    assertThat(event.orderId()).isEqualTo(orderId);
                    assertThat(event.sku()).isEqualTo("SKU-001");
                    assertThat(event.quantity()).isEqualTo(2);
                });
    }
}
```

**Điểm sáng của fixture:** Không cần `Customer` entity, payment method, fulfillment graph, hay 20 existing orders. `@TestConfiguration` cung cấp chỉ các collaborators cần cho đường hành vi đang kiểm.

**Giới hạn kỹ thuật cần nhớ:**

- `@ApplicationModuleTest` bootstrap application context của module. Các beans **khác** trong module, ví dụ `OrderReadService` dùng `JdbcTemplate`, vẫn có thể yêu cầu test database hoặc bean replacement phù hợp. Annotation không tự bảo đảm context độc lập khỏi mọi infrastructure.
- `@Primary` giải quyết ưu tiên injection theo type khi có nhiều bean candidates, nhưng không xử lý trùng **bean name** hoặc mọi custom qualifier. Tùy Spring Boot version và wiring, có thể phải dùng test bean replacement đúng cơ chế project.
- `PublishedEvents` cho thấy có **ít nhất một** `OrderPlaced` phù hợp. `anySatisfy` không chứng minh *exactly one*. Nếu contract cần đúng số event, thêm assertion số lượng theo API `PublishedEvents` của phiên bản đang dùng.
- No-op writer phù hợp với **event contract test**; nó **không** chứng minh transaction, row đã commit hay event publication registry. Tách một DB integration test thật khi mục tiêu cần persistence.

### 7.2. Tách setup theo ranh giới thay vì một “super fixture”

| Mục tiêu | Data cần | Không cần chỉ vì “cho giống production” |
| --- | --- | --- |
| Unit: hết hàng | Command, stock=false, write/event recorders | Spring context, DB, payment |
| Module: event contract | Command, stock=true, writer stub, `PublishedEvents` | Customer graph, outbox/broker |
| DB: query filter | A1/A2/B1, IDs/cleanup | Hàng trăm orders, images, shipping |
| Event listener retry | Cùng eventId/payload qua 2 deliveries, receipt/effect | Hai eventIds random giả làm duplicate |
| Transaction rollback | Các rows nằm trong **cùng transaction**, fault tại bước cần test | Full application data dump |
| Structural `verify()` | Code/module metadata | **Không cần business fixture** |

Nếu bạn phải dựng cả hệ thống để kiểm một logic nhỏ, trước hết hỏi: “Đây có đúng là integration boundary cần kiểm không?” Nếu không, chuyển về unit test hoặc module test được cấu hình gọn hơn.

## 8. Những lúc fixture nhiều dữ liệu là **cần thiết**

Việc loại bỏ fixture chỉ vì nó dài có thể làm mất test fidelity. Mỗi dataset nên tương ứng với **một rủi ro cụ thể**.

### 8.1. Event redelivery: hai deliveries nhưng một logical event

Một fixture riêng cho hệ thống **có eventId trong hợp đồng** nên giữ nguyên event identity nhưng không buộc dùng cùng Java object. Ví dụ JUnit độc lập chỉ kiểm fixture semantics:

```java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class DuplicateDeliveryFixtureTest {

    record IdentifiedOrderEvent(
            UUID eventId, UUID orderId, String sku, int quantity) {}

    @Test
    void redeliveryHasSameLogicalIdentityAndPayload() {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        IdentifiedOrderEvent first = new IdentifiedOrderEvent(
                eventId, orderId, "SKU-001", 2);
        IdentifiedOrderEvent redelivery = new IdentifiedOrderEvent(
                first.eventId(), first.orderId(),
                first.sku(), first.quantity());

        assertNotSame(first, redelivery);
        assertEquals(first, redelivery);
    }
}
```

`IdentifiedOrderEvent` minh họa một **event contract khác** với `OrderPlaced` đơn giản ở mục 3. Test ở đây chỉ xác nhận **hai fixture instances mô tả cùng event**; consumer integration test còn cần giao hai lần, kiểm receipt và đúng **một committed effect**. Đừng rút gọn đến mức biến hai logical events thành một phép so mơ hồ theo `orderId` hoặc dùng hai random event IDs để giả lập redelivery.

### 8.2. Transaction rollback: cần dữ liệu ở **hai điểm ghi**

Nếu use case là “ghi order và outbox atomic”, fixture tối thiểu có thể gồm một order identity, một event identity và một fault tại bước ghi thứ hai. Test phải assert **0 committed order/0 committed outbox** sau rollback, rồi 1/1 sau retry thành công. Một test chỉ assert exception là chưa đủ.

Không cần thêm marketing campaign, contact address, loyalty history nếu chúng không tham gia transaction cần chứng minh.

### 8.3. Query có nhiều predicate: giữ từng negative control

Test `placedOrderIdsFor(customerA)` có ba rows là có chủ đích: A1 positive, A2 negative status, B1 negative customer. Xóa A2 để “giảm fixture” khiến bug quên status filter có thể lọt qua. Xóa B1 làm điều tương tự với customer filter.

Quy tắc tốt: **mỗi row phải có vai trò được đặt tên; đừng loại row chỉ vì nó không được trả về**. Chính row “không được trả về” có thể tạo ra khả năng phân biệt behavior đúng–sai.

### 8.4. Schema compatibility: giữ fixture lịch sử riêng

Khi public event/schema V2 thêm field, một V1 payload cố ý thiếu field có thể cần giữ để kiểm migration/upcaster. Không tự cập nhật **mọi** fixture thành V2 rồi vô tình xóa kiểm thử dữ liệu cũ.

Phân biệt:

- **Fixture happy path V2:** đủ fields theo contract hiện tại.
- **Fixture V1 lịch sử:** chỉ dùng trong compatibility/migration test có tên rõ.
- **Fixture lỗi:** dữ liệu cố ý vi phạm một constraint cụ thể.

Cả ba có thể nhiều hơn một fixture, nhưng mỗi cái tồn tại vì một **thất bại có ý nghĩa** mà nó cần phát hiện.

## 9. Refactor fixture mà không làm yếu khả năng phát hiện lỗi

Đừng bắt đầu bằng việc xóa 60 dòng setup và chạy thử xem suite có xanh không. Một quy trình có thể review được gồm năm bước:

### Bước 1 — Ghi rõ `Given–When–Then` và bug cần bắt

Ví dụ test hết hàng:

```text
Bug mục tiêu:
  Khi StockAvailability.hasStock(...) = false,
  service vẫn gọi OrderWriter hoặc publish OrderPlaced.

Given thực sự cần:
  command(sku=SKU-001, qty=2)
  stock=false
  write/event recorders rỗng

Then:
  OUT_OF_STOCK
  writer calls = 0
  OrderPlaced publications = 0
```

Nếu một fixture field không nằm trong đường kiểm này, đánh dấu nó là **candidate to remove**.

### Bước 2 — Chia setup thành cần thiết, đối chứng và nhiễu

| Nhóm | Hành động |
| --- | --- |
| Điều kiện bắt buộc để chạy | Giữ, đặt tên thể hiện nghĩa |
| Dữ liệu đối chứng để bắt bug | Giữ dù không được dùng trong expected result |
| State bị tạo chỉ vì shared `@BeforeEach` | Chuyển vào test thật sự sử dụng hoặc factory riêng |
| Dữ liệu ở module khác, chỉ được seed qua `internal` | Thiết kế stub/public API hoặc integration harness đúng phạm vi |
| Static mutable fixture | Tạo mới theo method, không reset shared toàn cục |

### Bước 3 — Loại dần, không đổi contract cùng lúc

Refactor test trong một thay đổi nhỏ:

1. Giữ cùng tên test, hành vi và assertions quan trọng.
2. Xóa hoặc thay bằng local stub từng fixture không tham gia test.
3. Sau mỗi nhóm thay đổi, xem test có còn FAIL nếu bug mục tiêu được tạo ra không.
4. Không thêm production default/`@NamedInterface` chỉ để fixture cũ chạy.
5. Nếu cần sửa production behavior, tách thành commit/tác vụ khác để dễ review.

### Bước 4 — Thử một lỗi âm tính có chủ đích

Trên nhánh thử, trong `OrderPlacementService.place` bỏ điều kiện kiểm stock; unit test hết hàng **phải FAIL**. Trong `OrderReadService` bỏ `status = 'PLACED'`; DB test ba rows **phải FAIL**. Khôi phục code đúng trước merge.

Đây là negative probe để xác nhận fixture sau khi rút gọn vẫn có **sức phân biệt**. Nó không thay thế một bộ mutation tests đầy đủ, nhưng rất hữu ích khi refactor setup lớn.

### Bước 5 — Review tên và phạm vi helper

Một test tốt nên đọc gần như câu nghiệp vụ:

```text
outOfStockDoesNotWriteOrPublish
  Given:  command + stock=false
  When:   place(command)
  Then:   OUT_OF_STOCK, no write, no publish
```

Đổi tên `createAllDependenciesForOrderTest()` thành `orderWithStockUnavailable()` chưa đủ nếu helper bên trong vẫn dựng DB, payment, shipping và customer graph mà test không dùng. Cần xem **thực sự helper khởi tạo những gì**, không chỉ đổi nhãn.

## 10. Quality gate: sau khi làm gọn, test phải vẫn được chạy và vẫn bắt lỗi

Một đợt làm gọn fixture chỉ thành công khi có **hai bằng chứng độc lập**:

1. **Behavioral tests** vẫn chứng minh nguyên nhân–hệ quả, bao gồm unit, module, event và database ở đúng tầng.
2. **Architectural verification** vẫn bảo vệ module dependencies, không bị bỏ qua vì test mới dùng fake hoặc test fixtures nằm ở package khác.

### 10.1. Structural test không cần dữ liệu nghiệp vụ

`src/test/java/com/example/shop/ModuleArchitectureTest.java`:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void moduleDependenciesRemainValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Không seed SQL, mock `StockAvailability` hay tạo `OrderCommands` cho test này. Nó phân tích các application modules và dependency rules, không chạy use case đặt hàng. Nếu `orders` import `inventory.internal` trái policy, `verify()` cần báo lỗi ngay cả khi unit/module tests đều PASS.

Không biến fixture nhỏ đi bằng cách nới `@ApplicationModule(allowedDependencies = ...)`, công bố thêm `@NamedInterface` cho package `internal` hoặc cho phép module khác dùng internal repository. Sửa test setup qua **public API** hoặc test harness đúng phạm vi; giữ structural gate độc lập.

### 10.2. Lệnh build minh họa

Với Maven Wrapper và JUnit Platform/Surefire được cấu hình:

```bash
# Kiểm chắc structural test được khám phá.
./mvnw -B -Dtest=ModuleArchitectureTest test

# Chạy vòng đời tests đã nối trong build.
./mvnw -B verify
```

Với Gradle Wrapper và `useJUnitPlatform()`:

```bash
./gradlew test --tests 'com.example.shop.ModuleArchitectureTest'
./gradlew check
```

Đây là **hai lựa chọn theo build tool**, không yêu cầu chạy cả hai. Maven `verify` không tự chạy mọi class `*IT` nếu chưa cấu hình Failsafe; Gradle `check` không tự bao gồm custom `integrationTest` task nếu chưa nối vào task graph. Kiểm test report và cấu hình subproject thật trước khi kết luận.

### 10.3. Một ma trận kiểm tra sau refactor

| Test | Đầu vào tối thiểu | Bug cố ý phải khiến FAIL |
| --- | --- | --- |
| `outOfStockDoesNotWriteOrPublish` | Command + stock=false + 2 recorders | Bỏ check stock |
| `availableStockWritesAndPublishesForThisOrder` | Command + stock=true + 2 recorders | Bỏ publish hoặc save |
| `filtersBothStatusAndCustomer` | 3 rows A1/A2/B1 | Bỏ status filter hoặc customer filter |
| `publishesOrderIdentityWithoutUnrelatedFixture` | Command + bean stubs + `PublishedEvents` | Event có sai ID/SKU/quantity |
| `moduleDependenciesRemainValid` | Không có business fixture | Import `inventory.internal` trái quy tắc |

Nếu sau khi làm gọn một test luôn PASS cả khi tạo lỗi mục tiêu, việc refactor đã vô tình loại bỏ dữ liệu đối chứng hoặc assertion then chốt.

### 10.4. Đọc CI output: “ít setup” không có nghĩa “ít tests”

Trước khi merge, kiểm:

- `ModuleArchitectureTest` và behavioral tests xuất hiện trong JUnit report với **số tests executed lớn hơn 0**.
- Unit tests không trở thành `@Disabled` hoặc “green” do test discovery filter sai.
- Module event test có Spring context hợp lệ; không bị thay bằng một test chỉ assert object fixture do chính test tạo.
- DB test chạy với schema migrations thực, không phải in-memory list/fake tự định nghĩa.
- Test suite không vô tình dùng cùng `orderId`/DB rows từ shared state khi chạy parallel.
- Exit code của test failures được phản ánh vào required CI check.

Không dùng `-DskipTests`, `-x test`, `ignoreFailures`, CI `continue-on-error: true` hoặc shell `|| true` để né một test khó boot do fixture quá lớn. Nếu cần giảm chi phí suite, chuyển đúng test không cần DB về unit tier; giữ integration tests bảo vệ transaction/schema trong gate thích hợp.

### 10.5. Khi full suite FAIL nhưng test riêng PASS

Đừng kết luận test cần thêm fixture. Hãy tìm:

- `@BeforeEach` hoặc `static` fixture có mutable state dùng chung.
- Spring `ApplicationContext` cache và singleton fake lưu dữ liệu qua methods.
- Database rows/queue/event publication còn sót từ scenario khác.
- IDs cố định giữa nhiều integration tests trên cùng schema.
- Cleanup xóa dữ liệu của test khác, hoặc asynchronous listener xử lý sau khi test đã kết thúc.

**Hướng sửa vẫn bám chủ đề:** Tạo state đúng **phạm vi test**, dùng ID riêng, cleanup chính xác và xóa setup không liên quan. Đừng thêm hàng chục rows chỉ để “ổn định” một test bị nhiễu bởi shared state.

## 11. Bài thực hành và checklist: xóa fixture nào, giữ fixture nào?

**Đề bài:** Bộ test `orders` đang dùng một helper `fullCheckoutFixture()`, mỗi lần tạo customer, billing profile, shipping address, inventory snapshot, campaign, payment gateway, 20 orders và event recorder. Nó được dùng cho ba tests: hết hàng, event được phát và lọc trạng thái đơn.

### Phần A — Viết lại ý định test

Đặt tên ba scenarios:

1. `outOfStockDoesNotWriteOrPublish` — kiểm decision + side effects.
2. `publishesOrderIdentityWithoutUnrelatedFixture` — kiểm event contract ở `@ApplicationModuleTest`.
3. `filtersBothStatusAndCustomer` — kiểm query DB.

Viết `Given–When–Then` trong tối đa vài dòng cho **mỗi** scenario; gạch chân dữ liệu nào liên quan tới nhánh cần kiểm.

### Phần B — Tách fixture theo test tier

1. Đối với unit test, thay `fullCheckoutFixture()` bằng `PlaceOrderCommand` và hai recorder cục bộ.
2. Đối với module test, dùng một test configuration cung cấp `StockAvailability` và `OrderWriter` phù hợp; quan sát `PublishedEvents`.
3. Đối với DB query, giữ **đúng ba rows**: positive A1 và hai negative controls A2/B1.
4. Không đưa SQL setup vào unit test và không dùng no-op repository làm bằng chứng persistence.
5. Không tạo helper dùng chung nếu constructor ngắn hơn và chỉ xuất hiện một lần.

### Phần C — Chứng minh fixture sau refactor vẫn có sức bắt lỗi

| Thao tác thử trên nhánh tạm | Test phải chuyển sang FAIL | Lý do |
| --- | --- | --- |
| Bỏ nhánh từ chối khi stock=false | Unit hết hàng | Test kiểm throw và không có side effects |
| Bỏ `publisher.publishEvent(event)` | Unit happy path + module event | Hai tests kiểm thực sự có event |
| Bỏ `status='PLACED'` khỏi SQL | DB query test | Row `A2` lộ bug |
| Bỏ `customer_id = ?` khỏi SQL | DB query test | Row `B1` lộ bug |
| Import `inventory.internal` từ `orders` | Architectural test | Module dependency trái contract |

Khôi phục source code đúng sau mỗi negative probe. Nếu test vẫn PASS, cần bổ sung đúng **assertion hoặc đối chứng bị thiếu**, không phục hồi toàn bộ fixture cồng kềnh.

### Phần D — Review chi phí và độ rõ

Ghi lại **trước và sau** cho mỗi test:

- Số objects/DB rows tạo ra trong `Given`.
- Số fields mà người đọc phải hiểu trước khi thấy `When`.
- Số resources bên ngoài test sử dụng (DB, broker, HTTP, file).
- Số assertions gắn trực tiếp với bug mục tiêu.
- Negative probes có chuyển test sang FAIL không?
- Tests có còn chạy độc lập và trong full suite/CI không?

Không cần đặt KPI “mỗi test tối đa 10 dòng”. Một test DB với ba rows, migrations và cleanup dài hơn unit test nhưng hợp lý vì đang kiểm một rủi ro khác.

### Checklist review fixture

- [ ] Tên test cho biết một hành vi hoặc một điều kiện lỗi cụ thể.
- [ ] Mỗi object/row trong `Given` có vai trò: input, điều kiện hoặc đối chứng.
- [ ] Có thể xóa dữ liệu không liên quan mà assertion/behavior không thay đổi.
- [ ] Những **negative controls** cần để bắt bug không bị xóa chỉ vì “không được trả về”.
- [ ] Unit test không boot Spring/DB khi collaborator local đã đủ.
- [ ] `@ApplicationModuleTest` chỉ dùng bean/data cần cho event contract, không giả làm DB integration.
- [ ] `PublishedEvents` quan sát sự kiện thật và kiểm các field quan trọng.
- [ ] DB test dùng migrations/schema thật, dữ liệu tối thiểu và cleanup đúng ID.
- [ ] Factory dùng tên gắn nghiệp vụ, không che default khó thấy hay tạo mutable shared fixture.
- [ ] Negative input được tạo ở tầng cần kiểm, không xuyên validation bằng reflection.
- [ ] Event redelivery/rollback/legacy data giữ những biến thể **có lý do cụ thể**, không giản lược sai semantics.
- [ ] Test không seed module khác qua `internal` chỉ để tiện setup.
- [ ] `ApplicationModules.verify()` chạy độc lập và không bị suppress.
- [ ] Negative probes chứng minh ít nhất những bug mục tiêu làm suite FAIL.
- [ ] CI reports xác nhận các tests cần thiết đã được thực thi, không skip hoặc nuốt lỗi.

### Tự kiểm tra

1. Tại sao một test có ít rows hơn lại có thể **yếu hơn** nếu bỏ negative control?
2. Với test hết hàng, những fixture nào ngoài command, stock result và side-effect observation là cần thiết?
3. `@BeforeEach` tạo customer/payment graph cho mọi method có hại gì nếu chỉ một method dùng?
4. Khi nào dùng named factory; khi nào constructor trực tiếp dễ đọc hơn?
5. Vì sao một `@ApplicationModuleTest` dùng writer no-op không thể chứng minh DB row đã commit?
6. Nếu test query chỉ có row `PLACED` của customer A, những implementation sai nào vẫn có thể PASS?
7. Khi refactor fixture, tạo negative probe nào để chứng minh test còn bắt được việc quên publish event?
8. Vì sao structural `ApplicationModules.verify()` không cần một `Order` fixture nào?

**Ghi nhớ:** Giảm fixture dư thừa là **loại bỏ dữ liệu không giúp giải thích hành vi hoặc phân biệt đúng–sai**, chứ không phải cắt bớt mọi object và assertion. Unit tests chỉ cần đúng collaborators; `@ApplicationModuleTest` chỉ cần đúng wiring/event contract; DB tests giữ những rows đối chứng cần thiết. Sau refactor, hãy thử những lỗi mục tiêu, chạy `ApplicationModules.verify()` và kiểm JUnit/CI reports để chắc bộ test **dễ đọc hơn mà không yếu đi**.
