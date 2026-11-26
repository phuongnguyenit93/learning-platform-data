# Tránh dùng một test type cho mọi rủi ro

> **Chương:** Test types  
> **Phạm vi học tập:** `SPRING_MODULITH_VERIFICATION_TESTING` — kiểm chứng ranh giới kiến trúc ứng dụng Spring Modulith, quan hệ phụ thuộc module, `@ApplicationModuleTest`, sự kiện, database, tích hợp và quality gate CI.  
> **Tư tưởng chính:** Không có một loại test nào đồng thời cho bằng chứng đáng tin cậy về logic nghiệp vụ, cấu trúc module, HTTP, persistence, transaction, sự kiện bất đồng bộ và khả năng phục hồi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **chỉ dùng unit test**, **chỉ dùng `@SpringBootTest`**, **chỉ dùng E2E**, hoặc **chỉ dùng `ApplicationModules.verify()`** đều để lại khoảng trống kiểm chứng.
2. Phân loại rủi ro theo **nguồn lỗi**, **tác động**, **khả năng xảy ra** và **điểm quan sát**, thay vì chọn test theo sở thích công cụ.
3. Lập danh mục test phù hợp cho ứng dụng Spring Modulith: unit, slice, application module, architectural, contract, event/integration, database và E2E.
4. Phân biệt **chứng minh có event được phát**, **transaction đã commit**, **listener đã xử lý xong**, và **sự kiện có thể được phục hồi khi lỗi**.
5. Chọn phạm vi Spring context nhỏ nhất còn đủ bằng chứng; hiểu trade-off giữa `@ApplicationModuleTest` và `@SpringBootTest`.
6. Thiết kế *negative control* để kiểm tra một test thực sự phát hiện loại lỗi mà nó được giao bảo vệ.
7. Xây dựng risk-based quality gate CI ngăn phụ thuộc sai và hồi quy mà không để test chậm làm tắc nghẽn phản hồi.

**Kết quả mong đợi:** Khi một pull request thay đổi module `orders`, bạn không trả lời “chạy toàn bộ `@SpringBootTest` là đủ”, mà xác định rõ mệnh đề nào cần unit test, mệnh đề nào cần architecture verification, event integration và E2E, cùng lý do.

## 2. Sai lầm “một test type cho mọi rủi ro”

Một nhóm có thể đã viết hàng trăm unit test nhưng deployment vẫn thất bại vì cấu hình Spring bean sai. Nhóm khác có hàng chục E2E test chạy xanh nhưng vẫn để module `billing` import trực tiếp repository nội bộ của `orders`. Có nhóm khởi động `@SpringBootTest` cho cả phép nhân hai số, khiến CI chậm trong khi một assertion đơn giản vẫn chưa kiểm tra đúng edge case.

Vấn đề không nằm ở việc loại test đó “dở”. Vấn đề nằm ở **phạm vi bằng chứng không khớp với mệnh đề cần chứng minh**.

### Bảy kiểu “đơn canh” dễ gặp

| Chỉ sử dụng… | Vẫn có thể xanh khi… | Vì sao còn khoảng trống? |
| --- | --- | --- |
| **Unit test với mock** | Bean Spring không khởi tạo được, JPA query sai | Mock không tái tạo wiring và persistence thật |
| **`@WebMvcTest`** | Service ghi sai DB hoặc không publish event | Web slice chỉ xác minh lớp MVC được nạp |
| **`@DataJpaTest`** | Controller xử lý JSON sai, listener không đăng ký | Persistence slice không đi qua các module khác |
| **`@ApplicationModuleTest` cho producer** | Consumer ở module khác không xử lý event | Context có thể không chứa listener consumer |
| **`ApplicationModules.verify()`** | Tổng tiền sai, exception sai, event thiếu | Phân tích dependency graph, không chạy use case |
| **`@SpringBootTest` cho tất cả** | Thời gian suite cao, khó khoanh vùng lỗi, thiếu edge case | Full context không tự tạo assertion đúng |
| **E2E happy path** | Duplicate event tạo side effect trùng; module boundary bị phá | Một luồng thành công không bao phủ mọi failure mode |

Mỗi loại test cho ra **một dạng quan sát**. Không nên gán cho kết quả xanh nhiều ý nghĩa hơn phạm vi mà test thực sự kiểm tra.

### “Đủ nhiều test” không bằng “đủ loại bằng chứng”

Giả sử một endpoint tạo đơn luôn trả `201 Created` dù việc lưu dữ liệu sau đó thất bại. Viết 50 test chỉ kiểm tra status `201` có thể vẫn bỏ sót lỗi. Một integration test kiểm tra order đã commit, và một event integration test quan sát task ở consumer, cho những bằng chứng khác biệt mà 50 assertion status không cung cấp.

Do đó, **test portfolio** (danh mục kiểm thử) cần đa dạng **theo rủi ro**, không phải đa dạng chỉ để có nhiều annotation.

## 3. Bắt đầu từ rủi ro, không từ annotation

Mẫu xác định một phép kiểm tra:

~~~text
Mệnh đề cần bảo vệ:
    "Sau khi đơn được commit, fulfillment có một task đúng orderId."

Rủi ro:
    Listener không chạy / transaction chưa commit /
    event payload sai / consumer ghi DB lỗi.

Kích thích (stimulus):
    Gọi placeOrder(...) bằng dữ liệu hợp lệ.

Điểm quan sát (oracle):
    Đọc task qua API fulfillment, đúng orderId.

Thành phần phải chạy thật:
    Producer + consumer + transaction + event dispatch + persistence.

Test type phù hợp:
    Integration test nhiều module; chờ điều kiện async có timeout.

Điều chưa chứng minh:
    Sự kiện vẫn sống sót khi restart;
    module không có phụ thuộc package trái quy tắc.
~~~

Chỉ khi hoàn thành bản mô tả như trên mới chọn công cụ. Nếu rủi ro là phép tính làm tròn, unit test có thể đủ. Nếu rủi ro là unique constraint PostgreSQL khi hai transaction cạnh tranh, test dùng H2 hoặc mock database có thể không đủ.

### Hai câu hỏi thiết yếu

**Câu hỏi 1: Lỗi thuộc tầng nào?** Logic, web adapter, JPA, Spring wiring, ranh giới module, event, transaction, network hay hạ tầng bên ngoài?

**Câu hỏi 2: Bằng chứng phải quan sát ở đâu?** Giá trị Java trả về, ngoại lệ, HTTP response, row trong DB, event đã publish, side effect ở consumer, hoặc dependency graph?

Một test được chọn đúng khi nó kích hoạt **tầng có thể lỗi** và assert **đầu ra có thể bác bỏ mệnh đề**.

## 4. Ma trận rủi ro → test type → bằng chứng

| Rủi ro thực tế | Test type ưu tiên | Assertion/bằng chứng | Loại không thay thế được |
| --- | --- | --- | --- |
| Tính tổng tiền sai | Unit | `BigDecimal` đúng cho dữ liệu biên | Không cần khởi động toàn ứng dụng |
| HTTP validation sai | `@WebMvcTest` | Status `400`, JSON lỗi theo contract | Unit service không kiểm tra MVC binding |
| JPA mapping/query sai | `@DataJpaTest` | Save/find/query và constraint | Mock repository không kiểm tra SQL |
| API module không khởi tạo đúng bean | `@ApplicationModuleTest` | Gọi public API qua bean thật | Unit test `new Service()` không kiểm tra wiring |
| Module phụ thuộc package `internal` sai | Architectural test | `ApplicationModules.verify()` phát hiện vi phạm | E2E xanh không chứng minh ranh giới |
| Module consumer dùng sai public API | Contract/integration test | Input/return/exception theo hợp đồng | Java compile không phát hiện thay đổi ngữ nghĩa |
| Producer quên phát event | Module test + `PublishedEvents` | Event đúng type/payload | Consumer mock không chứng minh publish thật |
| Event không được xử lý sau commit | Cross-module integration | Task xuất hiện sau commit | `PublishedEvents` không chứng minh consumer |
| Duplicate event tạo hai tác động | Reliability integration | Idempotency, retry state | Happy path một event không đủ |
| Query phụ thuộc PostgreSQL dialect | Testcontainers với PostgreSQL | SQL/migration/constraint đúng | H2 không đại diện hoàn toàn |
| Entry point HTTP không đi hết luồng | API E2E | POST rồi GET outcome, cùng ID | Gọi thẳng Java service không kiểm tra HTTP |
| Event mất sau restart | Durable publication/recovery test | Pending state được phục hồi và xử lý tiếp | In-process test không chứng minh durability |

Bảng trên không có nghĩa **một rủi ro luôn chỉ cần đúng một test**. Ví dụ thay đổi `OrderPlaced` có thể cần producer module test, event contract test, consumer integration test và architectural test để kiểm tra các khía cạnh khác nhau của cùng thay đổi.

## 5. Case study xuyên suốt: orders → fulfillment

Giả sử ứng dụng Spring Modulith bán hàng có hai module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/                              # application module
│   ├── OrderManagement.java             # public API
│   ├── OrderPlaced.java                 # public event
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── domain/OrderTotalCalculator.java
│       ├── web/OrderController.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/                         # application module
    ├── FulfillmentQueries.java          # public API
    └── internal/
        ├── OrderFulfillmentListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo chiến lược phát hiện module mặc định của Spring Modulith, `orders` và `fulfillment` là application module, package root mỗi module là API mặc định và package `internal` là phần implementation.

### Contract và luồng nghiệp vụ

- `OrderManagement.placeOrder(customerId, amount)` tạo đơn, trả `orderId`.
- `orders` publish `OrderPlaced(orderId)` trong transaction tạo đơn.
- `fulfillment` nhận event sau khi transaction tạo đơn commit và tạo task.
- `FulfillmentQueries.hasTask(orderId)` cho biết task đã xuất hiện.
- REST API `POST /api/orders` có thể dùng `OrderManagement` và `GET /api/fulfillments/{id}` có thể quan sát kết quả.

~~~mermaid
flowchart LR
    H["HTTP entry point"] --> O["orders service"]
    O --> DB1[("Orders DB")]
    O --> E["OrderPlaced"]
    E --> L["fulfillment listener"]
    L --> DB2[("Fulfillment DB")]
    L --> Q["FulfillmentQueries"]
    A["Architecture test"] -. "kiểm tra dependency<br/>và API boundary" .-> O
    A -. "kiểm tra dependency" .-> L
~~~

**Phân biệt chiều phụ thuộc:** Runtime đi từ orders đến fulfillment qua event, nhưng listener của `fulfillment` import kiểu `orders.OrderPlaced`, vì thế dependency tĩnh là **`fulfillment → orders`**. Module `orders` không cần import implementation của `fulfillment`.

### Các mệnh đề độc lập

| ID | Mệnh đề | Nếu chỉ có happy-path E2E thì sao? |
| --- | --- | --- |
| R1 | Tổng tiền và validation domain đúng | Có thể bỏ sót biên và tổ hợp dữ liệu |
| R2 | HTTP JSON/validation đúng | Có thể chỉ kiểm tra request hợp lệ |
| R3 | Order JPA mapping và query đúng | Có thể không thử constraint/SQL đặc biệt |
| R4 | Bean trong orders được lắp đúng | E2E có thể phát hiện nhưng chẩn đoán lỗi chậm |
| R5 | Ranh giới package/dependency hợp lệ | Có thể compile và E2E xanh dù import sai |
| R6 | Event đúng type/payload được publish | E2E có thể báo timeout, khó chỉ ra publisher |
| R7 | Consumer xử lý sau commit | Cần quan sát side effect, không chỉ response POST |
| R8 | Duplicate/retry không tạo side effect trùng | Một event thành công không chứng minh |
| R9 | HTTP journey hoạt động xuyên các module | Unit/module test không đi qua network entry point |

Bộ test nên phân công **mỗi rủi ro cho lớp gần nguồn lỗi nhất**, đồng thời giữ một số integration/E2E test nối các lớp với nhau.

## 6. Unit test cho rủi ro logic: nhanh nhưng có giới hạn

Ví dụ nghiệp vụ:

~~~java
package com.example.shop.orders.internal.domain;

import java.math.BigDecimal;

public final class OrderTotalCalculator {

    public BigDecimal total(BigDecimal unitPrice, int quantity) {
        if (unitPrice == null ||
                unitPrice.signum() < 0 ||
                quantity <= 0) {
            throw new IllegalArgumentException("Invalid line");
        }

        return unitPrice.multiply(
                BigDecimal.valueOf(quantity));
    }
}
~~~

JUnit test thuần Java:

~~~java
package com.example.shop.orders.internal.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderTotalCalculatorTest {

    private final OrderTotalCalculator calculator =
            new OrderTotalCalculator();

    @Test
    void uses_decimal_arithmetic() {
        assertThat(calculator.total(
                new BigDecimal("19.99"), 3))
                .isEqualByComparingTo("59.97");
    }

    @Test
    void rejects_non_positive_quantity() {
        assertThatThrownBy(() -> calculator.total(
                new BigDecimal("19.99"), 0))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

**Bằng chứng:** Logic tính tổng và validation với các input được thử đã đúng.

**Không chứng minh:** Spring DI, `@Transactional`, JPA mapping, HTTP routing hoặc event listener. Vì vậy **chỉ viết unit test** cho mọi rủi ro trong ứng dụng Spring Modulith là thiếu.

Ngược lại, gắn `@SpringBootTest` lên class trên nhưng vẫn chỉ gọi `new OrderTotalCalculator()` sẽ tạo Spring context mà không tăng phạm vi bằng chứng. Cần tránh lãng phí như vậy.

## 7. Slice test: bảo vệ adapter mà không khởi tạo cả ứng dụng

### 7.1. Web adapter: @WebMvcTest

Nếu cần chứng minh một request HTTP thiếu `customerId` bị từ chối, web slice cho phép chạy Spring MVC mapping, Bean Validation và JSON binding, còn service có thể được thay bằng mock.

~~~java
package com.example.shop.orders.internal.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import com.example.shop.orders.OrderManagement;

@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderManagement orders;

    @Test
    void rejects_blank_customer_id() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"customerId":"","amount":100.00}
                        """))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Giả định:** `OrderController` có request DTO với `@Valid` và ràng buộc `@NotBlank` cho `customerId`. Đây là trích đoạn minh họa test cho controller đã tồn tại, không phải toàn bộ source của controller.

`@MockitoBean` được giới thiệu trong Spring Framework 6.2 (thường Spring Boot 3.4+); các dự án Boot cũ có thể dùng `@MockBean`. Chọn annotation phù hợp với version thực tế.

**Điều đã chứng minh:** Trong MVC slice đã cấu hình, request bị từ chối bằng status `400`. **Điều chưa chứng minh:** Service và repository thật hoạt động. Mock là lựa chọn đúng ở đây vì **service nằm ngoài điều đang kiểm tra**.

### 7.2. Persistence adapter: @DataJpaTest

Nếu rủi ro là entity mapping, repository query hoặc database constraint, hãy dùng persistence slice:

~~~java
package com.example.shop.orders.internal.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orders;

    @Test
    void saves_and_finds_an_order() {
        var saved = orders.save(
                new OrderEntity("CUS-01"));

        orders.flush();

        assertThat(orders.findById(saved.getId()))
                .isPresent();
    }
}
~~~

**Giả định:** `OrderEntity` có constructor nhận `customerId` và repository được định nghĩa phù hợp. `@DataJpaTest` thường dùng transaction rollback cho test method và có thể thay datasource bằng embedded database theo cấu hình.

**Điều đã chứng minh:** JPA mapping và hoạt động của repository trong database test. **Điều chưa chứng minh:** Một event consumer được gọi sau commit, vì transaction của test có thể rollback.

### Rủi ro khác nhau cần slice khác nhau

- `@JsonTest` phù hợp cho serialization/deserialization.
- `@RestClientTest` phù hợp cho adapter HTTP client và response mapping.
- `@WebMvcTest` phù hợp cho MVC contract trong phạm vi slice.
- `@DataJpaTest` phù hợp cho persistence adapter.

Không dùng riêng `@WebMvcTest` để tuyên bố SQL query đúng, và không dùng `@DataJpaTest` để tuyên bố REST API trả JSON đúng.

## 8. Architectural test: bảo vệ điều mà test hành vi có thể bỏ sót

Rủi ro đặc thù của Spring Modulith là một module truy cập implementation nội bộ của module khác, dù mã vẫn biên dịch.

Ví dụ tham chiếu sai trong module `fulfillment`:

~~~java
// Vi phạm ranh giới mặc định của module orders:
import com.example.shop.orders.internal.persistence.OrderEntity;
~~~

`OrderEntity` có thể khai báo Java `public`, nhưng nó **không nằm trong public API** của application module `orders`. Một E2E test tạo đơn vẫn có thể xanh dù dependency này tồn tại.

Bài kiểm thử kiến trúc:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void module_dependencies_and_packages_are_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` phân tích mô hình module và các quy tắc kiến trúc, như vòng phụ thuộc, truy cập package ngoài API và giới hạn dependency được khai báo.

### Giới hạn dependency có chủ đích

Giả sử `fulfillment` chỉ được phép phụ thuộc vào `orders`. Có thể đặt trong `fulfillment/package-info.java`:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Cần cập nhật khi kiến trúc thật sự thay đổi; không thêm mọi module vào whitelist chỉ để test xanh.

**Bằng chứng:** Quan hệ phụ thuộc và khả năng truy cập module API hợp lệ theo mô hình được phát hiện. **Không chứng minh:** Service được inject đúng hoặc business logic hoạt động. Do đó **chỉ dùng `ApplicationModules.verify()`** là không đủ cho các rủi ro runtime.

### Negative control

Trong nhánh thực hành, cố ý cho `fulfillment` tham chiếu `orders.internal.persistence.OrderEntity`, rồi chạy `ModuleArchitectureTest`. Test phải đỏ và chỉ ra quan hệ sai. Sau đó hoàn nguyên. Nếu không đỏ, cần kiểm tra package detection, named interfaces và quy tắc đang được áp dụng.

## 9. @ApplicationModuleTest: chứng minh module thật vận hành

`@ApplicationModuleTest` nằm giữa unit/slice test và full integration. Nó khởi động Spring context với phạm vi application module và dependency theo bootstrap mode.

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrdersModuleTest {

    @Autowired
    OrderManagement orders;

    @Test
    void creates_order_through_public_api() {
        long id = orders.placeOrder("CUS-02");

        assertThat(id).isPositive();
    }
}
~~~

Đoạn này giả định module có `OrderManagement.placeOrder(String)` và datasource/test fixture phù hợp. Trong bài test thực, nên xác minh thêm trạng thái order qua API truy vấn của module; **chỉ assert ID dương là bằng chứng tương đối yếu**.

### Ba phạm vi bootstrap

| Mode | Những module được đưa vào context | Nên dùng khi |
| --- | --- | --- |
| `STANDALONE` | Module đặt test | Use case nội bộ không cần dependency thật |
| `DIRECT_DEPENDENCIES` | Module đặt test và dependency trực tiếp | Cần contract/bean thật ở module được gọi |
| `ALL_DEPENDENCIES` | Module đặt test và dependency bắc cầu | Luồng cần một chuỗi dependency theo thiết kế |

Một test đặt trong `orders` với `DIRECT_DEPENDENCIES` **không tự nạp `fulfillment`** chỉ vì `fulfillment` đang subscribe `OrderPlaced`. Quan hệ tĩnh là `fulfillment → orders`; khi chọn bootstrap mode phải xét **chiều dependency của module chứa test**.

**Lạm dụng mode rộng:** Chuyển mọi test sang `ALL_DEPENDENCIES` hoặc `@SpringBootTest` chỉ để hết lỗi thiếu bean khiến suite chậm hơn, và có thể che một dependency/module boundary được thiết kế sai.

## 10. PublishedEvents: bằng chứng về publisher, không phải consumer

Nếu `orders` publish `OrderPlaced`, một module test có thể quan sát event:

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderPublicationTest {

    @Autowired
    OrderManagement orders;

    @Test
    void publishes_order_placed_for_new_order(
            PublishedEvents events) {

        long id = orders.placeOrder("CUS-03");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }
}
~~~

**Giả định:** `orders.OrderPlaced` là kiểu event công khai có method `orderId()`; `OrderManagement` đã publish sự kiện trong use case; test có datasource phù hợp.

**Bằng chứng:** Ít nhất một `OrderPlaced` đã được publish với payload phù hợp. `anySatisfy(...)` không chứng minh **chính xác một event**; muốn bảo vệ cardinality cần thêm assertion số lượng theo API version đang dùng.

**Không chứng minh:** Producer đã commit, listener consumer đã chạy, side effect đã commit, event registry bền vững hay retry qua restart. Nếu câu hỏi là “fulfillment đã tạo task chưa?”, phải dùng test khác.

### Ranh giới contract sự kiện

`OrderPlaced` nên nằm ở public API của `orders`, không mang JPA entity, repository hoặc kiểu nội bộ. Nếu event bị đổi type/field, có thể cần contract test về payload và serialization khi đưa ra broker ngoài JVM. Architectural test giúp phát hiện import sai, nhưng không kiểm tra ngữ nghĩa của event payload.

## 11. Integration test: chứng minh consumer xử lý sau commit

Một rủi ro khác hẳn producer publication là: **listener có đăng ký và side effect có xuất hiện không?**

Giả sử `fulfillment` có listener `@ApplicationModuleListener` nhận `OrderPlaced`, tạo task và công bố `FulfillmentQueries.hasTask(orderId)`. Với cấu hình Spring Modulith phù hợp, listener này thường thực thi bất đồng bộ và sau khi transaction của producer commit, trong transaction riêng.

Integration test cần cả hai module và database:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.example.shop.orders.OrderManagement;
import com.example.shop.fulfillment.FulfillmentQueries;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrdersFulfillmentIntegrationTest {

    @Autowired
    OrderManagement orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void creates_task_after_order_commit() {
        long orderId = orders.placeOrder("CUS-04");

        await()
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() ->
                        assertThat(fulfillment.hasTask(orderId)).isTrue());
    }
}
~~~

Đây là **khung test cho ứng dụng đã có repository, transaction manager, listener và datasource**. Nó sẽ không chạy độc lập nếu những thành phần đó chưa được triển khai.

**Bằng chứng:** Trong context và infrastructure test, lệnh tạo đơn dẫn đến task có thể đọc được qua API consumer. Awaitility chờ một điều kiện thực, có giới hạn; không phụ thuộc vào `Thread.sleep(...)`.

### Tại sao không đặt @Transactional lên test?

Nếu test **gọi bean trực tiếp** và có `@Transactional`, transaction service thường tham gia transaction của test, sau đó test framework có thể rollback. Listener chạy ở pha `AFTER_COMMIT` sẽ không nhận một commit thật. Bài test trên để transaction do service quản lý tự commit.

Nếu test gửi request HTTP qua embedded server, transaction phía server và test client là những boundary khác nhau; `@Transactional` của test client không tự rollback database mà server đã commit. Cần biết mình đang kiểm thử loại boundary nào.

### Cạm bẫy assertion âm

Một assertion `assertThat(fulfillment.hasTask(id)).isFalse()` ngay sau rollback **không tự chứng minh** rằng task sẽ không xuất hiện sau đó. Với asynchronous listener, cần test rollback/dispatch theo cơ chế phù hợp, quan sát transaction state hoặc publication registry và kiểm soát window/synchronization của test.

## 12. Reliability test: duplicate, retry và database thật

**Rủi ro:** Listener nhận cùng event nhiều lần do retry, concurrent delivery hoặc replay. Một happy-path integration test không chứng minh idempotency.

~~~text
Event OrderPlaced(42) lần 1 → fulfillment_task(order_id=42)
Event OrderPlaced(42) lần 2 → phải không gây side effect trùng
~~~

### Những ca cần kiểm tra

| Ca | Bằng chứng mong muốn |
| --- | --- |
| Hai lần nhận tuần tự | Vẫn chỉ một task hợp lệ; handler không lỗi không xử lý |
| Hai lần nhận đồng thời | Không phát sinh hai task; xử lý duplicate race hợp lệ |
| Consumer thất bại tạm thời | Trạng thái/retry theo hợp đồng đã cấu hình |
| Producer rollback | Không có side effect thuộc transaction bị rollback |
| Restart trước khi xử lý xong | Publication pending được khôi phục nếu yêu cầu durability |
| Event schema thay đổi | Consumer đọc được hoặc từ chối theo chính sách compatibility |

**Tại sao “đếm row = 1” chưa đủ?** Nếu database có unique constraint nhưng lần xử lý thứ hai ném ngoại lệ liên tục, dữ liệu cuối cùng vẫn chỉ một row nhưng cơ chế retry có thể mắc kẹt. Test phải xác minh cả **kết quả nghiệp vụ và failure handling** theo policy.

Ví dụ race condition:

~~~text
Listener A: existsByOrderId(42) -> false
Listener B: existsByOrderId(42) -> false
Listener A: INSERT(42) -> commit
Listener B: INSERT(42) -> unique violation
~~~

Một thiết kế production cần database constraint và thao tác idempotent phù hợp, có thể là upsert hoặc xử lý duplicate exception an toàn. Không giả định “kiểm tra trước khi insert” đủ trong mọi tình huống đồng thời.

### Durable publication registry

Spring Modulith hỗ trợ quản lý event publications với các adapter bền vững khác nhau. **Khả năng persist, resubmit và retry phụ thuộc adapter, dependency và cấu hình cụ thể.** Một test chỉ chạy trong JVM không chứng minh sự kiện sống sót qua restart.

Nếu rủi ro kinh doanh là mất đơn giao hàng khi ứng dụng crash, phải có test failure/restart với storage thật được giữ lại, không chỉ `PublishedEvents`.

### Database đúng với rủi ro

H2 phù hợp để kiểm tra nhanh một số mapping/flow, nhưng không đại diện hoàn toàn cho PostgreSQL về SQL dialect, locking, isolation và constraint. Khi rủi ro nằm ở các tính chất đó, dùng PostgreSQL Testcontainers hoặc database tương thích production.

Việc dùng Testcontainers làm test chậm hơn là một **chi phí đổi lấy bằng chứng thực tế**, không phải tối ưu kém. Điều sai là dùng container cho phép nhân đơn giản, hoặc mock database khi muốn kiểm tra race/transaction thật.

## 13. Contract test: compiler xanh không có nghĩa API còn đúng

Hai module có thể import đúng public interface nhưng vẫn không tương thích về **ngữ nghĩa**.

Ví dụ module `inventory` công bố:

~~~java
package com.example.shop.inventory;

import java.util.Optional;

public interface StockAvailability {

    /**
     * Empty if SKU is unknown.
     * Throws IllegalArgumentException if quantity is not positive.
     */
    Optional<Boolean> canReserve(String sku, int quantity);
}
~~~

Nếu implementation đổi từ `Optional.empty()` thành `Optional.of(false)` với SKU không tồn tại, chữ ký Java không đổi và `ApplicationModules.verify()` vẫn có thể xanh. Nhưng module consumer có thể xử lý hai trạng thái theo nghiệp vụ khác nhau.

**Provider contract test** nên inject bean thật của API và assert input/return/exception theo hợp đồng. **Consumer-facing test** nên chạy use case của module sử dụng API với provider thật (khi cần chứng minh tương tác), ví dụ:

~~~java
package com.example.shop.ordering;

import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(
        mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrderingInventoryContractTest {
    // Đặt trong module ordering,
    // gọi API của ordering và xác minh kết quả
    // nhận qua public API của inventory.
}
~~~

Đoạn trên là khung lựa chọn bootstrap, không phải test hoàn chỉnh. Nó giả định module `ordering` phụ thuộc trực tiếp `inventory`. Nếu cấu trúc module không có quan hệ đó thì mode này không tự đưa inventory vào context.

**Không dùng kiến trúc verification thay cho behavioral contract test.** Cũng không dùng provider mock test làm bằng chứng rằng provider thật thực hiện hợp đồng.

## 14. E2E test: cần nhưng không nên gánh mọi trường hợp

Khi yêu cầu là “client gửi HTTP thực, cuối cùng đọc được kết quả ở endpoint công khai”, dùng API E2E với embedded server:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderJourneyE2ETest {

    @Autowired
    TestRestTemplate http;

    @Test
    void order_reaches_fulfillment_via_http() {
        var response = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "CUS-E2E",
                       "amount", 120.00),
                JsonNode.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        long orderId = response.getBody()
                .path("orderId").asLong();

        assertThat(orderId).isPositive();

        await().atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    var result = http.getForEntity(
                            "/api/fulfillments/{id}",
                            JsonNode.class,
                            orderId);

                    assertThat(result.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(result.getBody()
                            .path("orderId").asLong())
                            .isEqualTo(orderId);
                });
    }
}
~~~

**Giả định:** REST controllers, JSON contract, event listener và database đã được ứng dụng triển khai. Trên CI phải dùng dữ liệu không đụng nhau giữa các test, ví dụ customer ID sinh riêng. Ví dụ trên minh họa cấu trúc E2E; cần điều chỉnh endpoint, authentication, body và schema theo hợp đồng thực tế.

**Bằng chứng:** HTTP request đi qua entry point, bean Spring, transaction, event và endpoint đọc kết quả trong môi trường test. **Không chứng minh:** Browser/UI hoạt động nếu không có browser, hoặc dịch vụ ngoài nếu chúng bị fake, hoặc mọi lỗi duplicate/retry.

### Vì sao không dồn hết assertion vào E2E?

- Khởi động toàn ứng dụng, database và HTTP server thường tốn chi phí lớn hơn unit/slice.
- Khi E2E timeout, có nhiều nguồn lỗi: MVC, service, JPA, event, thread pool, transaction, listener, query.
- E2E có thể chỉ kiểm tra một dữ liệu happy path, bỏ sót dữ liệu biên.
- E2E chạy xanh dù module import class nội bộ trái quy tắc.

Giữ một số **journey nghiệp vụ trọng yếu** làm E2E quality gate, còn phần lớn logic và contract nên được kiểm tra gần nguồn lỗi.

## 15. Chọn đúng hỗn hợp theo thay đổi cụ thể

Không phải mọi pull request đều cần viết một test mới ở mỗi lớp. Hãy chọn theo **thay đổi và rủi ro mới**.

| Thay đổi | Test ưu tiên | Test bổ sung khi cần |
| --- | --- | --- |
| Đổi công thức tính thuế | Unit với edge cases | Module test nếu wiring/currency policy thay đổi |
| Thêm validation JSON | Web slice | API E2E nếu thay public contract quan trọng |
| Đổi query JPQL sang native PostgreSQL | JPA integration với PostgreSQL | Module integration test cho use case |
| Di chuyển class qua module package | `ApplicationModules.verify()` | Module test cho bean wiring mới |
| Đổi signature public `OrderManagement` | Compile + provider/consumer contract | E2E nếu thay HTTP contract |
| Đổi payload `OrderPlaced` | Producer `PublishedEvents` + consumer contract | Integration test với real listener |
| Đổi listener sang async sau commit | Cross-module transaction/event integration | Rollback/failure timing tests |
| Thêm retry event | Registry/reliability integration | E2E cho luồng thiết yếu |
| Thêm security cho endpoint | Web/security slice | HTTP E2E với credential test thật |
| Nâng Spring Boot/Modulith | Context/module/architecture + integration smoke | E2E trên luồng trọng yếu |

**Quy tắc ưu tiên:** Đặt test ở nơi việc thay đổi có thể thất bại, rồi thêm một cấp cao hơn để chứng minh đường nối khi dependency/transaction/giao thức là phần rủi ro.

Không có tỷ lệ phần trăm unit/integration/E2E cố định áp dụng cho mọi dự án. Một ứng dụng event-driven nặng persistence sẽ cần nhiều integration tests hơn một thư viện thuật toán thuần Java.

## 16. Thiết kế danh mục kiểm thử theo “lỗ hổng bằng chứng”

Một danh mục cân bằng cho case study có thể như sau:

| Test | Rủi ro chính | Điểm quan sát | Điều chưa chứng minh |
| --- | --- | --- | --- |
| `OrderTotalCalculatorTest` | Logic tiền | `BigDecimal` | Spring wiring |
| `OrderControllerWebTest` | MVC validation | `MockMvc` status/JSON | Repository thật |
| `OrderRepositoryTest` | JPA mapping | Query/flush | Event consumer |
| `OrdersModuleTest` | Module wiring/use case | `OrderManagement` | HTTP entry point |
| `ModuleArchitectureTest` | Dependency/package | `ApplicationModules.verify()` | Business behavior |
| `OrderPublicationTest` | Producer contract | `PublishedEvents` | Consumer commit |
| `OrdersFulfillmentIntegrationTest` | Giao tiếp sau commit | `FulfillmentQueries.hasTask(id)` | Durability khi restart |
| `FulfillmentRetryTest` | Idempotency/retry | DB state + publication state | Mọi loại lỗi ngoài đời |
| `OrderJourneyE2ETest` | HTTP journey | POST + eventual GET | Mọi edge case |
| `PublicApiContractTest` | Hợp đồng API Java | Method result/exception | Wire format broker ngoài |

Không nên xem bảng này như lệnh “phải viết đúng mười class”. Nó là **bản đồ mệnh đề** để đánh giá coverage theo risk. Một tổ chức có thể kết hợp vài mệnh đề vào một class nếu không làm mờ bằng chứng, nhưng nên giữ tên test và assertion riêng biệt.

### Truy vết bằng chứng

~~~mermaid
flowchart TD
    R["Danh sách rủi ro"] --> CL["Mệnh đề có thể kiểm chứng"]
    CL --> OR["Oracle & observation"]
    OR --> UT["Unit / slice"]
    OR --> MT["Module / architecture"]
    OR --> IT["Integration / reliability"]
    OR --> ET["E2E"]
    UT --> CI["CI gates"]
    MT --> CI
    IT --> CI
    ET --> CI
~~~

Một mệnh đề bị bỏ trống ở bảng là tín hiệu cần xem xét, không được che bằng cách ghi “đã chạy `@SpringBootTest`” mà không có assertion tương ứng.

## 17. Quality gate CI: đa dạng theo rủi ro, không chỉ theo tốc độ

Một pipeline có thể phân lớp để trả kết quả sớm và vẫn giữ các phép kiểm tra nặng cần thiết:

~~~mermaid
flowchart LR
    PR["Pull request"] --> F["Fast gate<br/>unit + architecture"]
    F --> M["Module gate<br/>slice + @ApplicationModuleTest"]
    M --> I["Integration gate<br/>DB + event + contract"]
    I --> E["Critical E2E / reliability"]
    E --> D{"Tất cả gate<br/>bắt buộc đạt?"}
    D -- "Có" --> OK["Cho phép merge/release"]
    D -- "Không" --> FIX["Sửa lỗi"]
~~~

| Gate | Lỗi chính cần bắt | Gợi ý cadence |
| --- | --- | --- |
| **Unit** | Logic, validation, edge case | Mọi PR |
| **Architectural verification** | Import sai API, vòng phụ thuộc, allowedDependencies | Mọi PR; bắt buộc |
| **Slice** | HTTP/JPA/JSON adapter | Mọi PR |
| **Module** | Spring wiring và use case trong module | Mọi PR cho module bị tác động |
| **Contract** | API Java/event không tương thích | Mọi PR liên quan hoặc toàn bộ suite |
| **Cross-module integration** | Transaction, listener, DB | Mọi PR cho luồng trọng yếu |
| **Reliability** | Duplicate/retry/durable publication | CI có hạ tầng phù hợp; trước merge/release theo rủi ro |
| **E2E** | Request từ entry point tới outcome cuối | Chọn các journey thiết yếu |

### Không dùng chạy chậm làm lý do xóa kiểm tra kiến trúc

Architectural test với `ApplicationModules.verify()` không cần khởi tạo Spring context; nó thường là gate có chi phí hợp lý. Nếu CI chậm, đo lại context cache, database/container startup và những `@SpringBootTest` không cần thiết trước khi bỏ coverage.

### Nhưng cũng không đưa mọi test vào một job duy nhất

Tách unit/architecture và integration/E2E thành job có thể giúp trả phản hồi nhanh, nhưng phải đảm bảo job bắt buộc được chạy. Kiểm tra test discovery/tags/includes để không vô tình bỏ qua lớp kiểm tra. Song song nhiều job có thể tốn thêm tài nguyên và cold context/container startup, vì vậy cần đo theo môi trường thật.

### Kiểm soát flakiness

Event test bất đồng bộ phải chờ một **điều kiện cụ thể có timeout**; không dùng `Thread.sleep(...)` cố định. Database fixture phải cô lập, không phụ thuộc thứ tự test. Khi timeout, lưu log của publisher, listener, transaction và database để phân tích.

Đừng vô hiệu hóa một reliability test “flaky” mà không điều tra race, shared state, executor hoặc cấu hình CI. Một test không ổn định có thể cho thấy thiết kế bất đồng bộ đang có rủi ro thật.

## 18. Những phản mẫu cần nhận diện khi review pull request

| Câu khẳng định trong review | Vì sao chưa đủ | Câu hỏi cần hỏi lại |
| --- | --- | --- |
| “Có 100% unit coverage nên không cần integration.” | Unit mock bỏ qua wiring/database/event | Những dependency runtime nào chưa được chạy thật? |
| “E2E xanh nên package dependency chắc đúng.” | Java `public` có thể cho import vào `internal` | `ApplicationModules.verify()` đang chạy không? |
| “`PublishedEvents` có OrderPlaced nên shipping đã xử lý.” | Publisher khác consumer | Task nào đã commit và quan sát ở đâu? |
| “`@SpringBootTest` cho mọi test là an toàn nhất.” | Context đầy đủ không sửa assertion yếu | Có thể dùng unit/slice/module để giảm chi phí mà vẫn đủ bằng chứng? |
| “H2 xanh thì PostgreSQL cũng xanh.” | Dialect/constraint/locking khác nhau | SQL/migration nào phải chạy trên DB tương thích? |
| “Không thấy task ngay sau rollback nên chắc không có event.” | Async chưa chạy cũng cho `false` | Đã quan sát pha commit/dispatch thế nào? |
| “Unique key đảm bảo idempotency hoàn toàn.” | Concurrent duplicate vẫn có thể gây lỗi/retry | Handler có xử lý duplicate an toàn? |
| “Không cần contract test, compiler đã kiểm tra type.” | Ngữ nghĩa có thể đổi mà signature giữ nguyên | Return/exception/payload có còn đúng kỳ vọng? |
| “Test chạy lâu, bỏ gate này.” | Mất bằng chứng nếu gate bảo vệ rủi ro thực | Bottleneck là context, container hay test logic? |

**Quy tắc khi review:** Mỗi câu “đã được test” cần kèm **test nào, quan sát gì, trong môi trường nào và điều gì chưa được chứng minh**.

## 19. Bài thực hành

### Bài A — Chia rủi ro cho đúng test type

Cho các yêu cầu sau:

1. Tổng tiền không dùng `double` gây sai số.
2. Controller trả HTTP 400 nếu thiếu customerId.
3. `orders` không import `fulfillment.internal`.
4. `OrderPlaced` chứa đúng orderId.
5. Listener sau commit tạo task.
6. PostgreSQL unique constraint chặn task trùng.
7. Event còn có thể được phục hồi sau restart.
8. Client tạo đơn qua HTTP và đọc task qua HTTP.

Với mỗi yêu cầu, chọn test type nhỏ nhất **đủ bằng chứng**, mô tả oracle và nêu một điều mà test không chứng minh.

### Bài B — Bắt lỗi của cách “chỉ dùng unit test”

Một nhóm viết `OrderApplicationServiceTest`, mock `OrderRepository` và `ApplicationEventPublisher`. Tất cả test xanh, nhưng production không tạo được bean listener fulfillment.

Hãy đề xuất thêm ít nhất hai phép kiểm tra: một bài module/integration liên quan tới Spring wiring, một bài integration quan sát side effect của consumer. Giải thích vì sao unit mock test vẫn hữu ích và không cần xóa nó.

### Bài C — Bắt lỗi của cách “chỉ dùng E2E”

Một E2E test gửi POST và GET thành công. Sau đó developer import trực tiếp `orders.internal.persistence.OrderEntity` từ module `fulfillment`. Hãy viết `ModuleArchitectureTest` và cho biết vì sao E2E không bắt buộc thất bại.

Tiếp theo, tạm tạo vi phạm trong nhánh thực hành để xác nhận test kiến trúc đỏ rồi hoàn nguyên.

### Bài D — Bắt lỗi của cách “chỉ dùng PublishedEvents”

Producer test quan sát `OrderPlaced` đúng type và ID. Consumer listener bị bỏ `@ApplicationModuleListener` nhưng producer test vẫn xanh.

Hãy viết integration test đi qua hai module, có transaction commit và Awaitility chờ `FulfillmentQueries.hasTask(orderId)`. Chỉ ra điểm khác biệt giữa **event published** và **event handled**.

### Bài E — Thiết kế test chống duplicate

Giả sử `fulfillment` dùng `existsByOrderId(...)` rồi `save(...)`. Thiết kế test giao lại cùng event tuần tự và test chạy đồng thời. Đề xuất cơ chế idempotency ở database và cách xác minh lỗi duplicate được xử lý theo policy, thay vì chỉ đếm row.

### Bài F — Lập quality gate cho một PR

PR thay đổi `OrderPlaced`, JPA query và cấu hình listener async. Lập bảng gồm:

- Mệnh đề/rủi ro mới.
- Test cần chạy.
- Hạ tầng bắt buộc: Spring context, DB, registry/broker.
- Assertion có thể bác bỏ mệnh đề.
- Job CI và điều kiện merge/release.

Không chấp nhận một hàng chỉ ghi “`@SpringBootTest`” mà không nói rõ bằng chứng.

### Rubric tự đánh giá

| Tiêu chí | Chưa đạt | Đạt |
| --- | --- | --- |
| Phân loại rủi ro | Chỉ liệt kê công cụ | Chỉ rõ failure mode và impact |
| Chọn test type | Mặc định một loại cho tất cả | Phạm vi nhỏ nhất còn đủ bằng chứng |
| Assertion | Chỉ kiểm tra không có exception | Kiểm tra output/state/vi phạm cụ thể |
| Giới hạn | Khẳng định test xanh nghĩa là mọi thứ đúng | Nêu rõ non-claims của từng test |
| Kiến trúc | Bỏ qua `verify()` | Có test ranh giới độc lập |
| Bất đồng bộ | `sleep` cố định hoặc assert quá sớm | Await condition, transaction thật, timeout |
| CI | Có test nhưng có thể bị skip | Job được chạy và bắt buộc đúng theo rủi ro |

## 20. Checklist tránh “một test type cho tất cả”

- [ ] Đã viết mệnh đề kiểm chứng theo rủi ro, không chỉ theo annotation muốn dùng.
- [ ] Đã có unit test cho logic thuần Java và các edge case quan trọng.
- [ ] Đã dùng slice test để xác minh adapter thực mà không cần toàn ứng dụng.
- [ ] Đã kiểm tra bean wiring và behavior ở phạm vi module khi cần.
- [ ] Đã chạy `ApplicationModules.verify()` để bảo vệ package/API/allowedDependencies.
- [ ] Đã có contract test cho public API hoặc sự kiện có consumer quan trọng.
- [ ] Đã phân biệt producer event với consumer side effect.
- [ ] Đã xác nhận transaction commit thật khi test listener sau commit.
- [ ] Đã có chiến lược database thực/production-like cho SQL và constraint quan trọng.
- [ ] Đã kiểm tra duplicate/retry/idempotency khi event có thể được giao lại.
- [ ] Đã giữ E2E cho những hành trình công khai có giá trị, không thay toàn bộ test cấp thấp.
- [ ] Đã ghi rõ mock/fake nào được dùng và bằng chứng nào vì thế chưa có.
- [ ] Đã có negative control cho rule và test then chốt.
- [ ] Đã đưa các test vào CI theo mức rủi ro và tránh tình trạng bị skip.
- [ ] Đã đo chi phí Spring context/Testcontainers trước khi cắt giảm coverage.

## 21. Ghi nhớ

**Đừng dùng một test type cho mọi rủi ro.** Unit test giúp bảo vệ logic nhanh và rõ; slice test xác minh adapter; `@ApplicationModuleTest` kiểm tra wiring/use case trong module; `ApplicationModules.verify()` bảo vệ ranh giới dependency; contract test kiểm tra API module; integration test chứng minh transaction, event và consumer; reliability test bảo vệ retry/idempotency; E2E kiểm tra hành trình qua entry point công khai.

Một danh mục kiểm thử tốt không cần mọi test đều lớn, cũng không chỉ cần các test nhỏ. Nó cần **đúng bằng chứng ở đúng tầng**, với giới hạn được nói rõ và quality gate CI đủ mạnh để ngăn phụ thuộc sai lẫn hồi quy hành vi trong Spring Modulith.
