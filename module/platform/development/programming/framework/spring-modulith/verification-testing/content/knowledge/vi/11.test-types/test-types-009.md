# Chọn test type theo bằng chứng cần thu

> **Chương:** Test types  
> **Chương trình:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Mục tiêu thực hành:** Chọn đúng cấp kiểm thử để chứng minh ranh giới kiến trúc của Spring Modulith, hành vi của module, giao tiếp sự kiện, dữ liệu và các luồng tích hợp; biến những bằng chứng đó thành quality gate có thể chạy trong CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chuyển một yêu cầu chung như “module đặt hàng phải hoạt động đúng” thành các **mệnh đề kiểm chứng** cụ thể, có đầu vào và kết quả quan sát được.
2. Chọn **test type nhỏ nhất nhưng đủ độ trung thực** cho từng mệnh đề, thay vì mặc định dùng `@SpringBootTest` cho mọi thứ.
3. Phân biệt **evidence** (bằng chứng do assertion tạo ra), **assumption** (giả định môi trường test), **coverage** (phạm vi đã kiểm tra) và **blind spot** (điều chưa được chứng minh).
4. Áp dụng bảng quyết định cho unit test, slice test, `@ApplicationModuleTest`, architecture verification, contract test, event-driven integration test và E2E test.
5. Phân loại việc kiểm thử giao tiếp bất đồng bộ theo **publish / commit / consumer / durable delivery**, không dùng một assertion để suy ra toàn bộ.
6. Thiết kế ma trận truy vết giữa yêu cầu, rủi ro, bài test và quality gate CI.
7. Tránh các kiểu test “xanh nhưng thiếu bằng chứng”, đặc biệt với mock, H2, test transaction rollback và event listener bất đồng bộ.

**Thông điệp cốt lõi:** Đừng bắt đầu bằng câu hỏi “nên dùng annotation gì?”. Hãy bắt đầu bằng **“Tôi cần chứng minh điều gì và phải quan sát được dấu hiệu nào để kết luận?”**. Sau đó mới chọn môi trường test và công cụ Spring Modulith thích hợp.

## 2. Tư duy evidence-first: từ mệnh đề đến test type

Một câu như “module `orders` được kiểm thử đầy đủ” không phải tiêu chí có thể xác minh. Cần chuyển nó thành những phát biểu có thể bị bác bỏ bằng test:

- “`orders` không truy cập lớp `inventory.internal`.”
- “Với hai sản phẩm đơn giá 120,00 và số lượng 3, tổng tiền là 360,00.”
- “Request `POST /api/orders` thiếu `customerId` nhận HTTP 400.”
- “Lệnh đặt hàng hợp lệ tạo một bản ghi order.”
- “Khi order được commit, `OrderPlaced` được publish với đúng ID.”
- “Module `fulfillment` cuối cùng có task cho order vừa tạo.”
- “Nếu transaction tạo order rollback, listener hậu commit không tạo task.”
- “Nếu consumer nhận lại cùng event, side effect vẫn tuân thủ quy tắc idempotency.”

Mỗi phát biểu đòi hỏi một **điểm quan sát** khác nhau.

### Công thức lựa chọn

~~~text
YÊU CẦU
   ↓ Viết lại thành mệnh đề kiểm chứng có thể sai
MỆNH ĐỀ / RỦI RO
   ↓ Xác định đầu vào và kết quả quan sát được
BẰNG CHỨNG CẦN THU
   ↓ Xác định thành phần bắt buộc phải chạy thật
PHẠM VI THỰC THI TỐI THIỂU
   ↓ Chọn test type, fixture và assertion
TEST THỰC THI
   ↓ Ghi rõ điều chứng minh được và chưa chứng minh được
QUALITY GATE
~~~

Một **bộ mô tả bằng chứng** có thể viết theo mẫu:

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Claim** | Điều gì bắt buộc phải đúng? |
| **Stimulus** | Input, thay đổi mã hay sự kiện nào kích hoạt phép thử? |
| **Observation** | Đọc kết quả qua API, event, database, HTTP response hay dependency graph? |
| **Oracle** | Giá trị kỳ vọng hoặc invariant là gì? |
| **Required realism** | Thành phần nào phải thật: Spring MVC, transaction, JPA, broker, database? |
| **Isolation** | Thành phần nào được phép mock/fake mà không làm mất bằng chứng? |
| **Negative control** | Nếu cố ý đưa lỗi vào, test có thất bại không? |
| **Non-claims** | Những điều nào test này không chứng minh? |

Ví dụ mệnh đề “module `orders` không import implementation nội bộ của module khác” không cần mở HTTP server, database hay transaction. Đọc cấu trúc class/module là đủ. Vì vậy **architectural test bằng `ApplicationModules.verify()`** phù hợp và thường có chi phí thấp hơn integration/E2E test.

Ngược lại, mệnh đề “listener của `fulfillment` tạo task **sau commit**” không thể chứng minh bằng việc một mock event publisher nhận lời gọi. Nó cần transaction thật, listener được đăng ký, event dispatch và điểm quan sát side effect ở module consumer.

## 3. Ma trận chọn test type theo bằng chứng

| Bằng chứng cần thu | Test type ưu tiên | Quan sát/Assertion | Không tự chứng minh |
| --- | --- | --- | --- |
| Logic tính toán, validation thuần Java | **Unit test** | Return value, exception, invariant | Spring wiring, JPA, HTTP |
| Mapping request/response của MVC adapter | **`@WebMvcTest`** | HTTP status, JSON, validation, security policy trong slice | Service/JPA thật và luồng liên module |
| Query, entity mapping, constraint JPA | **`@DataJpaTest`** | Query result, mapping, flush/constraint | Controller và use case toàn module |
| Hợp đồng JSON độc lập | **`@JsonTest`** | Serialize/deserialize với mapper thực | HTTP routing hoặc database |
| HTTP client adapter tới dịch vụ ngoài | **`@RestClientTest`** hoặc test client tương ứng | Request/response/error mapping với mock server | Nhà cung cấp bên ngoài hoạt động thực |
| Module tự lắp bean và thực hiện use case | **`@ApplicationModuleTest`** | API module, dữ liệu, transaction, behavior | Mọi module khác đều được nạp |
| Quan hệ phụ thuộc, package API, vòng phụ thuộc | **Architectural test** | `ApplicationModules.verify()` pass/fail | Hành vi runtime |
| Contract provider/consumer dùng public API | **Module/contract test** | Kết quả và exception của API thật | Schema giao thức ngoài nếu chưa kiểm tra |
| Event được producer publish đúng | **`@ApplicationModuleTest` + `PublishedEvents`** | Kiểu và payload event | Listener đã xử lý hoặc commit |
| Side effect sau event giữa hai module | **Cross-module integration test** | State của consumer sau khi chờ điều kiện | Độ bền qua restart/broker ngoài |
| Retry, duplicate, idempotency, durable publication | **Reliability/integration test có hạ tầng phù hợp** | State, lỗi, publication registry, replay | Mọi loại lỗi production |
| Request đi qua HTTP entry point đến kết quả | **`@SpringBootTest(RANDOM_PORT)` / API E2E** | HTTP response và outcome downstream | Toàn bộ browser hoặc service ngoài nếu không chạy |
| Code Java ở các tầng phụ thuộc đúng chiều bên trong cùng module | **Custom ArchUnit rule** | Không có dependency trái chính sách | Hành vi của những class đó |

**Từ khóa quyết định không phải là tên framework, mà là bằng chứng.** Ví dụ cùng một phương thức `placeOrder` có thể xuất hiện trong unit, module, integration và E2E test, nhưng ở mỗi lớp nó chứng minh một vấn đề khác.

### “Test nhỏ nhất” không có nghĩa luôn “unit test”

Nếu câu hỏi chỉ là phép nhân `BigDecimal`, khởi tạo Spring và PostgreSQL là không cần thiết. Nhưng nếu câu hỏi là SQL unique constraint thực sự bảo vệ dữ liệu khi hai transaction cạnh tranh, mock repository hoặc H2 khác dialect có thể không tạo được bằng chứng đáng tin. Cần dùng database tương thích với production và tạo tình huống đồng thời thực tế.

**Nguyên tắc đủ độ trung thực:** Chỉ thay thế một thành phần bằng fake/mock khi hành vi thực của thành phần đó **không thuộc điều cần chứng minh**.

## 4. Cây quyết định thực tế

~~~mermaid
flowchart TD
    A["Tôi cần chứng minh điều gì?"] --> B{"Đó là quy tắc cấu trúc<br/>phụ thuộc/package?"}
    B -- "Có" --> V["ApplicationModules.verify()<br/>hoặc ArchUnit bổ sung"]
    B -- "Không" --> C{"Chỉ cần logic Java<br/>không cần Spring?"}
    C -- "Có" --> U["Unit test"]
    C -- "Không" --> D{"Chỉ một adapter<br/>HTTP/JPA/JSON/client?"}
    D -- "Có" --> S["Spring Boot slice test"]
    D -- "Không" --> E{"Hành vi nằm trong<br/>một module?"}
    E -- "Có" --> M["@ApplicationModuleTest"]
    E -- "Không" --> F{"Cần HTTP entry point<br/>thật?"}
    F -- "Có" --> H["@SpringBootTest<br/>RANDOM_PORT"]
    F -- "Không" --> I["Cross-module integration test"]
    I --> R{"Cần chứng minh<br/>replay/retry/restart?"}
    R -- "Có" --> P["Thêm registry/broker/database<br/>và failure injection phù hợp"]
    R -- "Không" --> T["Quan sát outcome thực<br/>ở consumer"]
~~~

Cây trên là **điểm bắt đầu**, không phải luật loại trừ tuyệt đối. Một yêu cầu có thể cần **nhiều test bổ sung** để thu đủ bằng chứng; ví dụ luồng event giữa module vừa cần structural verification, vừa cần producer contract test, vừa cần integration test về consumer.

Không chuyển thẳng sang `@SpringBootTest` mỗi khi gặp `NoSuchBeanDefinitionException`. Lỗi thiếu bean có thể chỉ ra rằng bạn đang cố chứng minh một việc ngoài phạm vi của slice/module test, hoặc dependency giữa module đã không đúng kiến trúc. Phân tích lại claim và phạm vi trước khi tăng context.

## 5. Case study xuyên suốt: orders và fulfillment

Giả sử ứng dụng bán hàng được chia thành hai application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderManagement.java          # public API
│   ├── OrderPlaced.java              # public event
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── web/OrderController.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java       # public API
    └── internal/
        ├── OrderPlacedListener.java
        ├── web/FulfillmentController.java
        └── persistence/
            └── FulfillmentTaskRepository.java
~~~

Trong cơ chế module mặc định của Spring Modulith, hai package `orders` và `fulfillment` là application module. Package root của mỗi module là API mặc định; `internal` chứa implementation không nên bị module khác import. Module `fulfillment` có thể import kiểu công khai `orders.OrderPlaced` để subscribe event, nhưng không được truy cập `orders.internal.persistence.OrderEntity`.

### Bộ yêu cầu

**R1 — Ranh giới:** `fulfillment` chỉ phụ thuộc public API của `orders`; không có vòng dependency.

**R2 — Tính giá:** Tổng tiền cho `quantity` hợp lệ phải đúng số học thập phân.

**R3 — HTTP:** Client gửi JSON không hợp lệ đến `POST /api/orders` phải nhận `400`.

**R4 — Use case:** Lệnh đặt hàng hợp lệ đi qua service/repository thật và tạo bản ghi.

**R5 — Event contract:** Khi đặt hàng thành công, `OrderPlaced` chứa đúng ID được publish.

**R6 — Giao tiếp:** Sau khi transaction orders commit, `fulfillment` tạo task cho cùng order.

**R7 — Độ tin cậy:** Khi nhận event trùng, không có hai task nghiệp vụ cho cùng order.

**R8 — E2E:** Client tạo order qua HTTP rồi đọc được kết quả fulfillment qua HTTP.

Tám mệnh đề này không nên gộp thành một E2E test rất lớn. Thay vào đó, mỗi mệnh đề có một hoặc vài **phép kiểm tra chuyên biệt** để lỗi xuất hiện gần nguyên nhân nhất.

### Sơ đồ phạm vi bằng chứng

~~~mermaid
flowchart LR
    HTTP["HTTP request"] --> WC["orders web adapter"]
    WC --> OMS["OrderManagement"]
    OMS --> REPO[("Orders JPA")]
    OMS --> EVT["OrderPlaced"]
    EVT --> LIST["fulfillment listener"]
    LIST --> FDB[("Fulfillment JPA")]
    FDB --> QUERY["FulfillmentQueries"]
    A["Architecture verification"] -. "module graph" .-> OMS
    M["Module test"] -. "orders wiring" .-> REPO
    P["PublishedEvents"] -. "publisher contract" .-> EVT
    I["Integration test"] -. "consumer outcome" .-> QUERY
    E2E["HTTP E2E"] -. "public journey" .-> HTTP
~~~

Đây là **bản đồ coverage**, không phải giả định rằng mọi kết quả đều được chứng minh bởi bất kỳ một test riêng lẻ nào.

## 6. Ví dụ bằng chứng R1: kiểm chứng dependency/package

**Mệnh đề:** Không có dependency ngoài API module, không có vòng phụ thuộc bị cấm.

**Test type:** Architectural test dùng `ApplicationModules`.

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void dependencies_respect_application_module_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**Điểm quan sát:** Bài test thất bại khi dependency graph trong mô hình Spring Modulith vi phạm quy tắc áp dụng, chẳng hạn import class nội bộ của module khác hoặc vòng phụ thuộc.

**Negative control có chủ đích:** Trong một nhánh thực hành, thêm reference từ `fulfillment` tới `com.example.shop.orders.internal.persistence.OrderEntity` rồi chạy lại test. Test phải đỏ; sau đó hoàn nguyên. Nếu test vẫn xanh, cần kiểm tra phạm vi phát hiện module và rule thực tế, chứ không vội kết luận cấu trúc đã được bảo vệ.

**Không chứng minh:** Bean Spring có được inject không, order được lưu chưa, event có đến fulfillment không. Vì vậy `verify()` không thay thế module/integration tests.

Nếu còn quy tắc **bên trong cùng module**, chẳng hạn controller không được gọi thẳng repository, cần ArchUnit tùy chỉnh. `ApplicationModules.verify()` chủ yếu bảo vệ ranh giới application module, không tự biết mọi luật phân tầng nội bộ của từng dự án.

## 7. Ví dụ bằng chứng R2: unit test quy tắc thuần Java

Giả sử domain có một class tính tổng:

~~~java
package com.example.shop.orders.internal.domain;

import java.math.BigDecimal;

public final class OrderTotalCalculator {

    public BigDecimal total(BigDecimal unitPrice, int quantity) {
        if (unitPrice == null ||
                unitPrice.signum() < 0 ||
                quantity <= 0) {
            throw new IllegalArgumentException(
                    "Invalid price or quantity");
        }

        return unitPrice.multiply(
                BigDecimal.valueOf(quantity));
    }
}
~~~

Test chỉ cần Java và JUnit:

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
    void multiplies_price_by_quantity_exactly() {
        assertThat(calculator.total(
                new BigDecimal("120.00"), 3))
                .isEqualByComparingTo("360.00");
    }

    @Test
    void rejects_zero_quantity() {
        assertThatThrownBy(() -> calculator.total(
                new BigDecimal("120.00"), 0))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

**Bằng chứng:** Phép tính và validation theo các đầu vào thử nghiệm là đúng. Không cần `@SpringBootTest` vì không có dependency Spring.

**Blind spot:** Có thể service thật không dùng class này, hoặc mapping JPA/HTTP truyền dữ liệu sai. Khi cần chứng minh kết nối, thêm module/slice/integration test theo R3–R4.

**Lưu ý tiền tệ:** `BigDecimal.compareTo` so sánh giá trị số mà không yêu cầu `scale` giống nhau; nếu hợp đồng đòi độ chính xác/làm tròn cụ thể, cần test riêng về `scale`, currency hoặc rounding policy.

## 8. Ví dụ bằng chứng R3: hợp đồng HTTP của adapter

**Mệnh đề:** Request thiếu trường bắt buộc phải nhận `400 Bad Request`.

Nếu mục tiêu chỉ là MVC mapping, validation và response, chọn `@WebMvcTest` thay vì khởi động toàn hệ thống.

Ví dụ giả sử `OrderController` phụ thuộc interface `OrderManagement` và đã khai báo `@Valid` cho request DTO:

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

Đây là **trích đoạn test cho adapter giả định đã tồn tại**, không phải toàn bộ mã của controller. Để test pass cần controller dùng Bean Validation tương ứng và các dependency validation có mặt. `@MockitoBean` thuộc Spring Framework 6.2+ (thường dùng từ Spring Boot 3.4+); các phiên bản Boot 3.2/3.3 thường dùng `@MockBean`. Chọn annotation theo phiên bản thực tế, không dùng đồng thời.

**Bằng chứng:** Spring MVC xử lý request, deserialization/validation và status trong web slice như mong đợi.

**Không chứng minh:** Bean service thật được inject và lưu dữ liệu; transaction/event thật hoạt động; HTTP server thật hay security thực tế ngoài phạm vi cấu hình test. Nếu có Spring Security filter, test cần chuẩn bị authentication/CSRF hoặc kiểm chứng chính sách quyền phù hợp. Không tắt security chỉ để đạt status kỳ vọng khi quyền truy cập là một phần của hợp đồng.

## 9. Ví dụ bằng chứng R4 và R5: application module test

### 9.1. Khi cần chứng minh wiring và persistence

**Mệnh đề R4:** Qua public API `OrderManagement`, module `orders` sử dụng service và repository thật để lưu và truy vấn dữ liệu.

Chọn `@ApplicationModuleTest` đặt trong package `com.example.shop.orders`. Mode mặc định `STANDALONE` tập trung vào module chứa test, phù hợp khi không cần bean từ module khác.

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
    void persists_order_through_public_api() {
        long id = orders.placeOrder("CUS-001");

        assertThat(orders.findById(id)).isPresent();
    }
}
~~~

Đây là **khung test minh họa hợp đồng**: giả định `OrderManagement` có `placeOrder(String)` trả ID và `findById(long)` trả `Optional`, đồng thời module có repository/transaction thực và datasource test đã cấu hình. Khi chép vào dự án, khai báo đúng API, entity, schema và datasource. Ý nghĩa của ví dụ là vị trí quan sát: **gọi public API và đọc lại qua public API**, không inject repository nội bộ của module khác.

**Bằng chứng R4:** Bean được Spring lắp ráp, flow thực thi ghi và đọc dữ liệu trong môi trường test. Nếu chỉ mock repository, không thể kết luận JPA mapping/query đã đúng.

### 9.2. Khi chỉ cần chứng minh event được publish

**Mệnh đề R5:** Tạo order hợp lệ làm publish `OrderPlaced` chứa ID đúng.

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
    void publishes_order_placed_with_generated_id(
            PublishedEvents events) {

        long id = orders.placeOrder("CUS-002");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }
}
~~~

Giả định `orders.OrderPlaced` là event public API với trường `orderId()`; datasource và service được cấu hình theo use case minh họa.

**Bằng chứng R5:** Producer publish một event đúng loại và payload quan sát được trong bài test. `anySatisfy` chứng minh **ít nhất một event phù hợp**, không phải “chính xác một event”. Nếu hợp đồng yêu cầu đúng một, bổ sung assertion số lượng với API phù hợp phiên bản thư viện.

**Không chứng minh:** Transaction producer đã commit khi event được quan sát; `fulfillment` được nạp; consumer đã xử lý; event được lưu bền và sẽ sống sót qua restart. Đây là một ví dụ quan trọng về việc assertion xanh nhưng phạm vi bằng chứng **không đủ** cho R6 hoặc R7.

### 9.3. Chọn BootstrapMode có ý thức

| Mode `@ApplicationModuleTest` | Phạm vi bootstrap | Khi nào nên chọn |
| --- | --- | --- |
| `STANDALONE` | Module có test | Chỉ muốn chứng minh behavior/wiring của chính module |
| `DIRECT_DEPENDENCIES` | Module có test và dependency trực tiếp của nó | Cần bean thật ở module mà test module phụ thuộc |
| `ALL_DEPENDENCIES` | Module có test và toàn bộ chuỗi dependency bắc cầu | Claim thực sự đi qua các dependency bắc cầu |

**Đọc đúng chiều dependency:** Nếu `fulfillment` import `orders.OrderPlaced` thì `fulfillment → orders` là dependency tĩnh. Test đặt trong `orders` với `DIRECT_DEPENDENCIES` **không tự nạp module fulfillment**, vì fulfillment là consumer phụ thuộc ngược về orders. Muốn chứng minh R6 phải chọn context có cả hai module, ví dụ integration test `@SpringBootTest` hoặc module test đặt tại package consumer với mode thích hợp nếu cây dependency cho phép.

## 10. Ví dụ bằng chứng R6: consumer thực sự xử lý sau commit

**Mệnh đề:** Khi `orders` tạo order và transaction commit, module `fulfillment` cuối cùng lưu một task cho đúng `orderId`.

Một producer test với `PublishedEvents` là chưa đủ. Cần một integration test bao gồm:

- Bean của hai module (producer và consumer).
- Transaction manager và database test.
- Event listener thực với semantics sau commit.
- API quan sát trạng thái ở consumer.
- Điều kiện chờ hữu hạn nếu handler bất đồng bộ.

Ví dụ sau giả định có API `FulfillmentQueries.hasTask(long)` và consumer được đăng ký bằng `@ApplicationModuleListener`:

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
    void creates_fulfillment_task_after_order_commit() {
        long id = orders.placeOrder("CUS-003");

        await()
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() ->
                        assertThat(fulfillment.hasTask(id)).isTrue());
    }
}
~~~

Bài test là **khung theo một ứng dụng đã có hai module, listener và database**, không phải một ứng dụng Spring Boot chạy độc lập chỉ nhờ đoạn code này. Dữ liệu test, migration/schema và concurrency cần được cấu hình rõ trong dự án. Awaitility có thể nằm trong `spring-boot-starter-test` tùy phiên bản; nếu thiếu hãy thêm dependency test thích hợp.

**Bằng chứng R6:** Một transaction tạo order thành công dẫn đến state quan sát được tại consumer trong môi trường test.

**Chưa chứng minh R7:** Tình huống không có lỗi vẫn có thể xanh nếu listener không idempotent. Cần bài test chuyên biệt về duplicate/replay.

### Vì sao không đặt @Transactional lên integration test này?

Với test **gọi service trực tiếp**, `@Transactional` trên test có thể khiến lệnh tạo order tham gia transaction của test và bị rollback khi test kết thúc. Listener dạng `AFTER_COMMIT` khi đó không chạy như trong luồng commit thật. Test trên không dùng `@Transactional` để lệnh của service có thể tự commit.

Ngược lại, nếu test gửi HTTP qua một server chạy ở thread khác, transaction của test client không tự bao transaction của server. Cần hiểu transaction boundary của từng kiểu test thay vì mặc định gắn `@Transactional` để “dọn dữ liệu”.

## 11. Ví dụ bằng chứng R7: duplicate, rollback và retry

**R7 khác R6:** R6 cần thấy task **xuất hiện**. R7 cần biết nếu cùng event được giao lại thì **không có side effect trùng** hoặc lỗi không kiểm soát.

Một bộ kiểm tra độ tin cậy cần phân chia theo sự cố:

| Sự cố giả lập | Bằng chứng cần | Môi trường phù hợp |
| --- | --- | --- |
| Event bị giao hai lần tuần tự | Chỉ một task/side effect, handler xử lý trùng an toàn | Consumer integration test và unique constraint |
| Hai event đồng thời cùng ID | Không có race làm vi phạm invariant hoặc retry vô hạn | Database/transaction concurrency test |
| Producer publish rồi rollback | Không có side effect hậu commit trái hợp đồng | Transaction integration test, kiểm tra commit/rollback |
| Consumer thất bại tạm thời | Publication được quản lý theo policy và hoàn thành sau retry | Durable publication registry + failure injection |
| Application restart giữa publish và consume | Event pending còn tồn tại và được xử lý lại sau restart nếu hợp đồng yêu cầu | Persistent registry/broker và test restart |
| Event payload đổi kiểu/field | Consumer hoặc serializer phát hiện incompatibility | Contract/schema tests |

**Chỉ quan sát “không có task ngay lúc này” không chứng minh task sẽ không xuất hiện sau đó.** Với hệ thống bất đồng bộ, assertion âm phải gắn với một cơ chế đồng bộ hoặc observation window có căn cứ, cùng hiểu biết về trạng thái event/transaction.

### PublishedEvents, retry và event registry không đồng nghĩa nhau

`PublishedEvents` phù hợp để thấy event đã **được publish** trong test module. Nó không phải bằng chứng rằng publication đã được persist trong durable registry, consumer xử lý xong hoặc retry/replay sau crash hoạt động.

Spring Modulith có các cơ chế hỗ trợ event publication registry, nhưng khả năng lưu bền và resubmission phụ thuộc adapter, dependency và cấu hình cụ thể. Nếu claim là “sự kiện tồn tại qua restart”, cần chạy test với storage bền vững và mô phỏng restart; chỉ test in-memory trong một JVM không đủ.

### Idempotency phải được thiết kế, không chỉ test

Unique key theo `orderId` có thể ngăn hai row trùng, nhưng hai handler đồng thời vẫn có thể gặp xung đột:

~~~text
A: existsByOrderId(42) -> false
B: existsByOrderId(42) -> false
A: INSERT(42) -> thành công
B: INSERT(42) -> unique violation
~~~

Vì thế, “không có hai row” chưa chứng minh hệ thống xử lý duplicate **êm và phục hồi tốt**. Có thể cần upsert, handling unique violation, event ID/version hoặc retry strategy phù hợp. Test reliability phải phản ánh hợp đồng được chọn.

## 12. Khi cần bằng chứng về database thật

Cùng một phép kiểm thử dữ liệu có thể có độ tin cậy khác nhau tùy database:

| Claim | Dùng H2 có thể đủ? | Khi nên dùng database cùng loại production |
| --- | --- | --- |
| Repository save/find cơ bản | Thường đủ cho phản hồi nhanh | Khi schema/migration có đặc tính riêng |
| JPA mapping của entity phổ biến | Có thể đủ để bắt nhiều lỗi | Khi dialect, type hoặc constraint khác biệt |
| Native SQL, JSONB, stored procedures | Thường không đủ | Nên dùng Testcontainers/DB phù hợp |
| Transaction isolation và locking | Không nên suy rộng | Cần chạy engine production-like |
| Unique constraint khi concurrency | H2 có thể minh họa | Cần DB thực và test cạnh tranh khi là rủi ro trọng yếu |
| Flyway/Liquibase production migrations | Hibernate auto-DDL không đủ | Chạy migration thật trên DB phù hợp |

Một module/integration test được viết với `@DataJpaTest`, `@ApplicationModuleTest` hoặc `@SpringBootTest` có thể dùng Testcontainers để có datasource chính xác hơn. Chọn test type theo **phạm vi hành vi** trước; chọn môi trường database theo **độ trung thực cần thiết** sau.

Không biến mọi unit test thành database test chỉ vì production có database. Chi phí test nên tỷ lệ với rủi ro mà nó giảm được.

## 13. Ví dụ bằng chứng R8: E2E qua entry point

**Mệnh đề:** Một HTTP client thực gửi `POST /api/orders` và cuối cùng quan sát được task fulfillment qua `GET /api/fulfillments/{id}`.

Nếu claim bao gồm **HTTP server** và hợp đồng public endpoint, chọn `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng HTTP client test. Ví dụ khung:

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
    void order_creation_reaches_fulfillment() {
        var created = http.postForEntity(
                "/api/orders",
                Map.of("customerId", "CUS-E2E"),
                JsonNode.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        long id = created.getBody().path("orderId").asLong();
        assertThat(id).isPositive();

        await()
                .atMost(Duration.ofSeconds(15))
                .untilAsserted(() -> {
                    var result = http.getForEntity(
                            "/api/fulfillments/{id}",
                            JsonNode.class, id);
                    assertThat(result.getStatusCode())
                            .isEqualTo(HttpStatus.OK);
                    assertThat(result.getBody()
                            .path("orderId").asLong())
                            .isEqualTo(id);
                });
    }
}
~~~

Đây cũng là **khung gắn với các endpoint của ứng dụng minh họa**; test cần các controller, schema và listener thật. Nếu API yêu cầu amount, authentication hoặc content type cụ thể, request phải tuân thủ hợp đồng đó; nên dùng ID/fixture riêng để tránh data collision khi chạy song song.

**Bằng chứng:** HTTP routing, deserialization, wiring, transaction, database, event và endpoint đọc kết quả phối hợp trong môi trường đã chạy.

**Không chứng minh:** UI/browser hoạt động; dịch vụ ngoài không được kết nối hoạt động; mọi giao tiếp phân tán đều tin cậy; dependency graph lành mạnh. Một E2E test lớn còn có thời gian chạy và chi phí chẩn đoán cao, nên không thay thế các test cấp thấp.

## 14. Những bẫy làm test xanh nhưng bằng chứng yếu

### 14.1. Mock sai điểm

~~~text
Claim: JPA repository truy vấn đúng.
Setup: mock repository rồi assert giá trị trả về đã stub.
Kết quả: test xanh nhưng KHÔNG kiểm tra SQL/JPA.
~~~

Mock phù hợp khi dependency nằm **ngoài** hành vi cần chứng minh. Ví dụ web slice cần mock service để chỉ kiểm tra MVC; nhưng JPA slice phải giữ repository thật. Khi muốn chứng minh module được Spring nối bean thật, không mock toàn bộ bean nội bộ có vai trò chính trong use case.

### 14.2. Dùng status 200 làm bằng chứng quá mức

~~~text
Claim: đơn được lưu và event được xử lý.
Assertion: POST /api/orders trả 200 hoặc 201.
Thiếu: kiểm tra dữ liệu đã commit và state consumer.
~~~

Response HTTP chỉ chứng minh mức độ tương ứng với status/response contract. Nếu luồng bất đồng bộ, response thành công thường chỉ có nghĩa **request đã được chấp nhận/xử lý ở bước đầu**, không chứng minh mọi tác vụ downstream hoàn tất.

### 14.3. Dùng PublishedEvents suy ra listener chạy thành công

~~~text
Claim: fulfillment đã có task.
Assertion: PublishedEvents chứa OrderPlaced.
Thiếu: consumer, transaction, persistence và outcome.
~~~

Cần integration test quan sát task, không chỉ event producer. Nếu yêu cầu retry qua restart, còn cần registry/broker thật trong môi trường test.

### 14.4. “Architecture verification xanh nên phần mềm đúng”

~~~text
Claim: ứng dụng tuân thủ ranh giới module.
Assertion: ApplicationModules.verify() không ném lỗi.
Kết luận hợp lệ: dependency graph đúng theo quy tắc mô hình.
Kết luận KHÔNG hợp lệ: mọi API, business logic, DB và event đều đúng.
~~~

Structural verification và behavioral tests bổ sung nhau. Một architecture gate tốt không thay cho JUnit test nghiệp vụ; một integration test xanh cũng không cho phép phá package boundary.

### 14.5. Test transaction rollback và thời điểm quan sát

Với listener hậu commit, test `@Transactional` có thể rollback transaction khi kết thúc. Điều đó dẫn đến listener không chạy dù production sẽ chạy khi transaction commit thật. Ngược lại, một assertion “không có state ngay” có thể xanh chỉ vì listener còn chậm.

Hãy viết rõ **transaction nào bắt đầu, transaction nào commit, event nào được publish, thời điểm nào được quan sát** trước khi kết luận.

### 14.6. Dùng embedded database để khẳng định tương thích production

H2 xanh không mặc nhiên xác nhận query, migration, locking hoặc constraint của PostgreSQL/MySQL. Nếu claim là “native SQL trên PostgreSQL xử lý đúng”, phải chạy PostgreSQL hoặc hạ tầng đủ tương thích; dùng Testcontainers là một lựa chọn thực tế.

## 15. Lập ma trận truy vết yêu cầu → bằng chứng → quality gate

Một dự án có thể lưu ma trận truy vết ở tài liệu engineering hoặc ticket để mọi người biết test nào bảo vệ rủi ro nào. Ví dụ cho case study:

| ID | Mệnh đề cần chứng minh | Test/file ví dụ | Bằng chứng assert | Gate |
| --- | --- | --- | --- | --- |
| R1 | Không vượt module API, không có vòng | `ModuleArchitectureTest` | `verify()` pass | Mọi PR |
| R2 | Logic tổng tiền và input đúng | `OrderTotalCalculatorTest` | Exact total, exception | Mọi PR |
| R3 | HTTP validation đúng | `OrderControllerWebTest` | Status 400, body nếu có contract | Mọi PR |
| R4 | Module lưu và truy vấn được | `OrdersModuleTest` | `findById(id)` có dữ liệu | Mọi PR |
| R5 | Producer publish event đúng | `OrderPublicationTest` | Event type, ID/payload | Mọi PR |
| R6 | Consumer tạo task sau commit | `OrdersFulfillmentIntegrationTest` | Await state consumer | Mọi PR cho luồng trọng yếu |
| R7 | Duplicate/retry không phá invariant | `FulfillmentReliabilityTest` | Unique side effect, recovery state | CI hạ tầng bắt buộc theo rủi ro |
| R8 | HTTP journey thực hoạt động | `OrderJourneyE2ETest` | POST + GET cùng ID | PR/deploy gate tùy mức độ |

**Không dùng số lượng test làm đại diện trực tiếp cho độ tin cậy.** Mười test chỉ assert cùng một status có thể tạo ít bằng chứng hơn ba test kiểm tra ba failure mode độc lập. Chất lượng nằm ở độ phù hợp của oracle và khả năng phát hiện lỗi mục tiêu.

### “Evidence card” cho một pull request

Mỗi thay đổi quan trọng có thể được rà soát qua mẫu ngắn:

~~~text
Change: Đổi cơ chế lưu OrderPlaced sang durable registry.
Claim mới: Event pending được giữ lại nếu consumer lỗi.
Test hiện có: OrderPublicationTest, OrdersFulfillmentIntegrationTest.
Gap: Chưa có test lỗi consumer và restart publication storage.
Test bổ sung: RegistryRecoveryIntegrationTest với persistent adapter.
Evidence: publication pending sau failure, completed sau resubmit.
Non-claim: broker ngoài không được kiểm tra nếu ứng dụng không dùng broker.
Gate: job integration-reliability bắt buộc trước release.
~~~

Mẫu này khiến quyết định test type minh bạch: ta chọn test vì **gap trong bằng chứng**, không vì vừa biết một annotation mới.

## 16. Tối ưu chi phí mà không làm mất bằng chứng

Có thể chia test thành những **lớp phản hồi**:

~~~mermaid
flowchart LR
    PR["Pull request"] --> FAST["Fast: unit + architecture"]
    FAST --> MED["Medium: slice + module contract"]
    MED --> SLOW["Integration: database + event"]
    SLOW --> CRIT["Critical E2E / reliability"]
    CRIT --> G{"Tất cả gate<br/>bắt buộc đạt?"}
    G -- "Có" --> M["Merge / release"]
    G -- "Không" --> F["Sửa, phân tích bằng chứng"]
~~~

| Lớp | Ưu tiên tối ưu | Không được đánh đổi |
| --- | --- | --- |
| Unit/architecture | Nhanh, chạy mọi PR | Assertions rõ, đúng module discovery |
| Slice | Context nhỏ, mock đúng boundary | Thành phần quyết định hành vi của slice phải thật |
| Module | Wiring và use case trong module | Không mock mất phần cần chứng minh |
| Cross-module | Kết quả cuối cùng, async wait hữu hạn | Transaction, event và consumer phải hiện diện |
| Infrastructure reliability | Database/broker/registry phù hợp | Failure injection và recovery phải thực tế |
| API E2E | Một số luồng nghiệp vụ thiết yếu | HTTP entry point và outcome public thực |

Không phải mọi bài test đắt tiền đều cần chạy ở mỗi lần sửa comment. Tuy nhiên, nếu một mệnh đề rủi ro cao là điều kiện merge/release, job bảo vệ mệnh đề đó phải **thật sự được chạy và được coi là bắt buộc**, không chỉ tồn tại trong repository.

### Một quy trình lựa chọn tiết kiệm

1. Viết claim và oracle trước.
2. Chọn phạm vi nhỏ nhất mà oracle vẫn có ý nghĩa.
3. Mock những dependency ngoài claim; giữ thật phần thuộc claim.
4. Chọn environment đủ trung thực, ví dụ PostgreSQL Testcontainers nếu SQL dialect là rủi ro.
5. Xác minh bằng một thay đổi sai có chủ đích rằng test phát hiện được lỗi.
6. Đưa test vào đúng CI job và xác định thời điểm cần chạy.
7. Xem lại test khi kiến trúc, event contract hoặc hạ tầng thay đổi.

## 17. Bài tập lựa chọn test type

### Bài 1 — Phân loại nhanh

Chọn **test nhỏ nhất đủ chứng minh** và ghi rõ assertion:

| Mệnh đề | Gợi ý hướng giải |
| --- | --- |
| Chiết khấu 10% phải được tính đúng | Unit test với ví dụ giá và số lượng |
| Controller trả 400 khi JSON thiếu field | `@WebMvcTest` kiểm tra validation |
| JPA native query chạy đúng trên PostgreSQL | Database integration/slice với PostgreSQL |
| Module `orders` không import `inventory.internal` | `ApplicationModules.verify()` |
| Service thật publish `OrderPlaced` đúng payload | `@ApplicationModuleTest` + `PublishedEvents` |
| Listener sau commit làm xuất hiện task | Cross-module integration + await state |
| Retry cùng một event không tạo task trùng | Reliability test với consumer và constraint thật |
| Client HTTP có thể tạo order và truy vấn trạng thái | `@SpringBootTest(RANDOM_PORT)` / API E2E |

**Yêu cầu thêm:** Với mỗi hàng, liệt kê **một điều test chưa chứng minh**. Ví dụ `@WebMvcTest` không mặc nhiên kiểm tra repository và event consumer.

### Bài 2 — Nhận diện bằng chứng thiếu

Một nhóm báo cáo: “`PublishedEvents` đã thấy `OrderPlaced`; vậy gửi email xác nhận chắc chắn thành công”. Hãy chỉ ra mệnh đề nào **được chứng minh**, mệnh đề nào **chưa**, và đề xuất test consumer với fake mail adapter hoặc integration với mail test server tùy hợp đồng. Nếu cần delivery guarantee qua restart, bổ sung kiểm tra registry hoặc broker tương ứng.

### Bài 3 — Chọn BootstrapMode

Giả sử `fulfillment` phụ thuộc `orders` thông qua public `OrderPlaced`. So sánh ba phương án:

- Test đặt trong `orders` với `STANDALONE`.
- Test đặt trong `fulfillment` với `DIRECT_DEPENDENCIES`.
- Integration test đặt ở root với `@SpringBootTest`.

Hãy xác định phương án nào **có thể** đưa bean của cả producer và consumer vào context, phương án nào không tự làm được, và vì sao direction của dependency là dữ kiện quyết định.

### Bài 4 — Thiết kế kiểm tra rollback

Một use case publish event rồi phát sinh lỗi và rollback. Hãy viết evidence card gồm claim, stimulus, observation, oracle, môi trường test và non-claims. Giải thích vì sao kiểm tra `shipping.hasTask(id) == false` **ngay sau rollback** có thể chưa đủ với listener async.

### Bài 5 — Dùng negative control

Chọn hai test của case study:

1. Architecture verification: cố ý thêm một import sai vào package nội bộ module khác.
2. Event publisher: cố ý bỏ lệnh `publishEvent(...)`.

Chạy đúng test tương ứng, xác nhận chúng đỏ, rồi hoàn nguyên. Nếu test không đỏ, điều chỉnh môi trường hoặc oracle trước khi tin tưởng quality gate.

### Bài 6 — Thiết kế CI cho một thay đổi

Tình huống: đội phát triển chuyển JPA query sang PostgreSQL native SQL và triển khai durable event publication registry. Hãy cập nhật ma trận truy vết:

- Bằng chứng mới về SQL dialect/migration cần test nào?
- Bằng chứng về restart/retry publication cần test nào?
- Architecture gate có cần giữ không?
- Test nào nên ở PR gate và test nào có thể chạy trong job hạ tầng riêng nhưng vẫn bắt buộc trước release?

### Đáp án định hướng

Không có một “đúng duy nhất” cho toàn bộ bài tập vì môi trường và hợp đồng khác nhau. Tuy nhiên, đáp án tốt phải chỉ ra **tính chất cần chứng minh**, **điểm quan sát**, **thành phần không được mock**, **kết quả kỳ vọng** và **giới hạn bằng chứng**. Nếu câu trả lời chỉ là tên annotation mà không có oracle, việc chọn test type chưa hoàn chỉnh.

## 18. Checklist trước khi chấp nhận bằng chứng kiểm thử

- [ ] Mệnh đề được phát biểu rõ, có điều kiện sai được.
- [ ] Test kích hoạt đúng entry point hoặc thành phần mà mệnh đề yêu cầu.
- [ ] Assertion quan sát được kết quả nghiệp vụ hoặc cấu trúc, không chỉ mock setup.
- [ ] Component quyết định tính đúng/sai của mệnh đề không bị mock đi.
- [ ] Môi trường (database, transaction, event registry, broker) đủ trung thực cho rủi ro.
- [ ] Với async, test chờ điều kiện có thời hạn và không dựa vào `Thread.sleep` cố định.
- [ ] Với rollback và duplicate, test kiểm tra đúng pha transaction và invariant.
- [ ] Architectural test không bị thay bằng behavioral test hoặc ngược lại.
- [ ] Có ít nhất một negative control hợp lý cho test/rule quan trọng.
- [ ] Test được CI phát hiện, thực thi và áp dụng đúng mức bắt buộc.
- [ ] Những điều test **không chứng minh** đã được ghi nhận để bổ sung khi cần.

Một bài test đáp ứng checklist không đảm bảo chương trình không có lỗi. Nó giúp nhóm diễn đạt chính xác **niềm tin dựa trên bằng chứng nào**, đồng thời nhận ra khoảng trống coverage trước khi sự cố xuất hiện.

## 19. Ghi nhớ

**Chọn test type theo bằng chứng cần thu** là cách tiếp cận trung tâm khi kiểm thử Spring Modulith. Unit test chứng minh logic Java; slice test chứng minh hợp đồng adapter; `@ApplicationModuleTest` chứng minh behavior và wiring trong module; `ApplicationModules.verify()` chứng minh các ranh giới dependency/package được tuân thủ; integration test kiểm tra transaction, event và kết quả giữa module; API E2E kiểm tra luồng qua entry point công khai.

Hãy **đặt mệnh đề, xác định oracle, chọn phạm vi tối thiểu, kiểm tra non-claims và đưa bằng chứng vào quality gate CI**. Với hệ thống bất đồng bộ, đặc biệt phải tách rõ publish, commit, consume và durable recovery. Một bộ test tốt không chỉ trả lời “xanh hay đỏ”, mà còn trả lời **“điều gì vừa được chứng minh, trong điều kiện nào và điều gì vẫn chưa được chứng minh?”**
