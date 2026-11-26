# Slice test cho lớp adapter trong module

> **Chương:** Test types  
> **Module học:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Chủ đề:** Kiểm thử một lát cắt hạ tầng của application module Spring Modulith bằng Spring Boot test slice.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định adapter nào nên kiểm thử bằng slice test và chọn annotation phù hợp như `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` hoặc `@RestClientTest`.
- Viết test cho web adapter với `MockMvc`, kiểm tra status, JSON và mapping dữ liệu mà không khởi động toàn bộ ứng dụng.
- Viết test cho persistence adapter bằng JPA slice, kiểm tra truy vấn, mapping từ entity sang đối tượng nghiệp vụ và hành vi với dữ liệu không tồn tại.
- Kiểm soát dependency của từng slice bằng mock, stub hoặc `@Import` một cách có chủ đích.
- Phân biệt slice test với unit test thuần Java, `@ApplicationModuleTest` và kiểm chứng kiến trúc bằng `ApplicationModules.verify()`.
- Đưa các test phù hợp vào quality gate CI nhằm phát hiện hồi quy của adapter, đồng thời giữ quy tắc phụ thuộc giữa các module.

**Ý chính:** Trong Spring Modulith, adapter đưa module tiếp xúc với HTTP, database, JSON hoặc hệ thống bên ngoài. Một **slice test** khởi tạo phần Spring cần thiết cho công nghệ của adapter, từ đó kiểm tra chính xác cách adapter chuyển đổi dữ liệu và giao tiếp với các thành phần liên quan. Slice test *không* tự kiểm chứng toàn bộ hành vi và ranh giới kiến trúc của application module.

## 2. Slice test là gì và nằm ở đâu trong kiến trúc module?

Một application module thường có logic nghiệp vụ và các lớp adapter làm nhiệm vụ giao tiếp với thế giới bên ngoài. Ví dụ module `ordering` nhận HTTP request, gọi một application port rồi truy vấn dữ liệu qua JPA:

~~~text
com.acme.shop
├── ShopApplication.java                    # @SpringBootApplication
└── ordering                               # application module
    ├── OrderQuery.java                    # API/port của module
    ├── OrderSummary.java                  # DTO nghiệp vụ
    └── internal                           # implementation nội bộ
        ├── web
        │   └── OrderController.java       # inbound HTTP adapter
        └── persistence
            ├── OrderJpaEntity.java
            ├── OrderJpaRepository.java
            └── JpaOrderQuery.java         # outbound JPA adapter
~~~

Sơ đồ các lời gọi ở runtime:

~~~mermaid
flowchart LR
    Client["HTTP client"] --> W["OrderController<br/>web adapter"]
    W --> P["OrderQuery<br/>port"]
    P -. "implemented by" .-> A["JpaOrderQuery<br/>persistence adapter"]
    A --> R["OrderJpaRepository"]
    R --> DB[("Database")]
~~~

Trong Spring Modulith, root package `com.acme.shop.ordering` là API công khai mặc định của module; các package con như `internal.web` và `internal.persistence` là implementation nội bộ. Các class nội bộ của **cùng** module có thể cộng tác với nhau, nhưng module khác không được tùy ý truy cập những package nội bộ đó. Nếu cần công bố các package khác, phải thiết kế named interface rõ ràng và xác minh quy tắc phụ thuộc.

**Các lát cắt thường gặp:**

| Adapter cần kiểm tra | Slice test | Thành phần được tập trung kiểm tra | Không được mặc nhiên kiểm tra |
| --- | --- | --- | --- |
| HTTP MVC controller | `@WebMvcTest` | Routing, validation, HTTP status, request/response body, MVC advice/filter được nạp | Service nghiệp vụ thật, JPA, toàn bộ module |
| JPA repository/adapter | `@DataJpaTest` | Entity mapping, Spring Data repository, query và giao dịch ở lớp JPA | HTTP, luồng ứng dụng đầy đủ, production DB mặc định |
| JSON serialization | `@JsonTest` | JSON mapper, serializer/deserializer | HTTP routing và xử lý nghiệp vụ |
| HTTP client adapter | `@RestClientTest` | HTTP client, request/response mapping với mock server phù hợp | Kết nối thật tới dịch vụ ngoài |
| JDBC adapter | `@JdbcTest` hoặc slice tương ứng | JDBC, SQL, database configuration nằm trong slice | MVC, các bean ngoài slice |

Slice test thường có khởi tạo Spring context, nhưng **context nhỏ hơn** `@SpringBootTest`. Mỗi annotation chỉ nạp những phần phù hợp với lát cắt, nên một dependency của adapter có thể chưa tồn tại trong test context dù vẫn tồn tại khi chạy ứng dụng thật. Đây là hành vi có chủ đích, và ta phải cung cấp dependency bằng mock, fake hoặc import đúng thành phần cần thiết.

## 3. Ví dụ 1: Kiểm thử web adapter với @WebMvcTest

Giả sử endpoint `GET /api/orders/{id}` phải trả về thông tin đơn hàng dạng JSON. Nếu không tìm thấy ID, controller trả `404 Not Found`. Controller chỉ làm nhiệm vụ chuyển dữ liệu HTTP sang lời gọi của port; chính sách nghiệp vụ thuộc phần khác của module.

### 3.1. Hợp đồng đầu vào của adapter

**`src/main/java/com/acme/shop/ordering/OrderSummary.java`**

~~~java
package com.acme.shop.ordering;

public record OrderSummary(String id, String customerId) {}
~~~

**`src/main/java/com/acme/shop/ordering/OrderQuery.java`**

~~~java
package com.acme.shop.ordering;

import java.util.Optional;

public interface OrderQuery {
    Optional<OrderSummary> findById(String id);
}
~~~

Đây là ví dụ port đọc dữ liệu đơn hàng trong cùng module `ordering`. Đặt interface này trong package API là một lựa chọn thiết kế cho tình huống minh họa; ở hệ thống thật, phạm vi public API cần dựa vào hợp đồng giữa các module.

### 3.2. Web adapter

**`src/main/java/com/acme/shop/ordering/internal/web/OrderController.java`**

~~~java
package com.acme.shop.ordering.internal.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.acme.shop.ordering.OrderQuery;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderQuery query;

    OrderController(OrderQuery query) {
        this.query = query;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderResponse> findById(@PathVariable("id") String id) {
        return query.findById(id)
                .map(order -> ResponseEntity.ok(
                        new OrderResponse(order.id(), order.customerId())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    public record OrderResponse(String id, String customerId) {}
}
~~~

Controller nằm trong `internal.web`; test của controller cũng đặt trong package đó để có thể truy cập class và constructor không public. DTO trả về được khai báo bằng `record`. Với Spring MVC hiện đại, Jackson có thể serialize các record có thuộc tính công khai.

### 3.3. Viết test chỉ nạp web slice

**`src/test/java/com/acme/shop/ordering/internal/web/OrderControllerWebTest.java`**

~~~java
package com.acme.shop.ordering.internal.web;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import com.acme.shop.ordering.OrderQuery;
import com.acme.shop.ordering.OrderSummary;

@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderQuery query;

    @Test
    void returns_order_as_json_when_found() throws Exception {
        when(query.findById("ORD-001")).thenReturn(
                Optional.of(new OrderSummary("ORD-001", "CUS-007")));

        mvc.perform(get("/api/orders/{id}", "ORD-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-001"))
                .andExpect(jsonPath("$.customerId").value("CUS-007"));

        verify(query).findById("ORD-001");
    }

    @Test
    void returns_404_when_order_does_not_exist() throws Exception {
        when(query.findById("ORD-404"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/orders/{id}", "ORD-404"))
                .andExpect(status().isNotFound());
    }
}
~~~

**Cơ chế:**

1. `@WebMvcTest(OrderController.class)` giới hạn phạm vi kiểm thử vào Spring MVC, gồm controller đã chỉ định cùng các thành phần web áp dụng cho slice.
2. `MockMvc` mô phỏng HTTP request và xử lý request qua Spring MVC mà không cần mở HTTP server thật.
3. `@MockitoBean` tạo/thay bean của `OrderQuery` trong test context, để tránh kéo adapter JPA và database vào web slice.
4. `when(...).thenReturn(...)` chuẩn bị dữ liệu cho ca test; `jsonPath` và `status` xác nhận hợp đồng HTTP. `verify(...)` chỉ dùng khi cần bảo đảm controller đã truyền đúng ID cho port.

**Lưu ý phiên bản:** `@MockitoBean` nằm trong Spring Framework 6.2+ (phổ biến với Spring Boot 3.4+). Với Spring Boot 3.2/3.3, ví dụ tương đương có thể dùng `@MockBean` từ `org.springframework.boot.test.mock.mockito.MockBean`. Không dùng đồng thời hai annotation. Hãy chọn theo phiên bản thực tế và theo API mà dự án đang hỗ trợ.

**Nếu ứng dụng có Spring Security:** web slice có thể nạp security filter và trả `401` hoặc `403` nếu request không được xác thực/ủy quyền. Khi đó, cần cấu hình ngữ cảnh bảo mật đúng cho test (ví dụ `@WithMockUser` khi có `spring-security-test`), hoặc cố ý kiểm tra response bảo mật. Chỉ vô hiệu hóa filter nếu **bảo mật thực sự không thuộc mục tiêu** của test và quyết định đó đã được ghi rõ. Endpoint GET trong ví dụ giả định người gọi có quyền truy cập.

### 3.4. Tăng chất lượng web slice

Bổ sung các test theo hợp đồng endpoint thực tế:

| Tình huống | Assertion nên có |
| --- | --- |
| Tài nguyên tồn tại | `200`, cấu trúc JSON, trường và giá trị |
| Tài nguyên không tồn tại | `404`, body theo hợp đồng |
| Input không hợp lệ | `400` khi có validation/controller advice xử lý |
| Người dùng không đủ quyền | `401`/`403` tùy security policy |
| API đổi field hoặc kiểu dữ liệu | Test JSON thất bại và báo lỗi hợp đồng |

Với endpoint nhận body, bổ sung test serialization/deserialization, `Content-Type` và validation `@Valid`. Đừng chỉ assert `200`: một controller có thể trả `200` nhưng JSON thiếu field, sai ID hoặc sai hình dạng dữ liệu.

## 4. Ví dụ 2: Kiểm thử persistence adapter với @DataJpaTest

Web test phía trên chứng minh phép chuyển đổi từ HTTP request sang `OrderQuery`. Nó **không** chứng minh `JpaOrderQuery` tìm đúng dữ liệu. Để kiểm tra adapter JPA, dùng một slice khác với entity, repository và database của test.

### 4.1. Entity và Spring Data repository

**`src/main/java/com/acme/shop/ordering/internal/persistence/OrderJpaEntity.java`**

~~~java
package com.acme.shop.ordering.internal.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
class OrderJpaEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String externalId;

    @Column(nullable = false)
    private String customerId;

    protected OrderJpaEntity() {
        // JPA requires a no-argument constructor.
    }

    OrderJpaEntity(String externalId, String customerId) {
        this.externalId = externalId;
        this.customerId = customerId;
    }

    String getExternalId() {
        return externalId;
    }

    String getCustomerId() {
        return customerId;
    }
}
~~~

**`src/main/java/com/acme/shop/ordering/internal/persistence/OrderJpaRepository.java`**

~~~java
package com.acme.shop.ordering.internal.persistence;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

interface OrderJpaRepository extends JpaRepository<OrderJpaEntity, Long> {
    Optional<OrderJpaEntity> findByExternalId(String externalId);
}
~~~

Đối với Spring Boot 3+, JPA dùng package `jakarta.persistence`. Nếu dự án dùng phiên bản cũ hơn, phải điều chỉnh import và dependency tương ứng.

### 4.2. Adapter thực hiện port

**`src/main/java/com/acme/shop/ordering/internal/persistence/JpaOrderQuery.java`**

~~~java
package com.acme.shop.ordering.internal.persistence;

import java.util.Optional;

import org.springframework.stereotype.Repository;

import com.acme.shop.ordering.OrderQuery;
import com.acme.shop.ordering.OrderSummary;

@Repository
class JpaOrderQuery implements OrderQuery {

    private final OrderJpaRepository repository;

    JpaOrderQuery(OrderJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<OrderSummary> findById(String id) {
        return repository.findByExternalId(id)
                .map(entity -> new OrderSummary(
                        entity.getExternalId(),
                        entity.getCustomerId()));
    }
}
~~~

Ở đây có hai trách nhiệm cần kiểm tra: truy vấn theo `externalId` và mapping từ `OrderJpaEntity` sang `OrderSummary`. Vì `@DataJpaTest` chỉ tự động nạp các thành phần JPA phù hợp, ta chủ động dùng `@Import` để đưa riêng adapter `JpaOrderQuery` vào context test.

### 4.3. Test JPA slice

**`src/test/java/com/acme/shop/ordering/internal/persistence/JpaOrderQueryTest.java`**

~~~java
package com.acme.shop.ordering.internal.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import com.acme.shop.ordering.OrderSummary;

@DataJpaTest
@Import(JpaOrderQuery.class)
class JpaOrderQueryTest {

    @Autowired
    OrderJpaRepository repository;

    @Autowired
    JpaOrderQuery adapter;

    @Test
    void maps_persisted_entity_to_order_summary() {
        repository.saveAndFlush(
                new OrderJpaEntity("ORD-001", "CUS-007"));

        assertThat(adapter.findById("ORD-001"))
                .contains(new OrderSummary("ORD-001", "CUS-007"));
    }

    @Test
    void returns_empty_when_no_order_matches() {
        assertThat(adapter.findById("ORD-404")).isEmpty();
    }
}
~~~

**Cơ chế:**

- `@DataJpaTest` khởi tạo JPA slice với entity, repository và các thành phần liên quan; không nạp MVC controller và phần lớn service thường của ứng dụng.
- `@Import(JpaOrderQuery.class)` bổ sung đúng adapter cần kiểm thử. Không dùng `@SpringBootTest` chỉ để có bean này.
- `saveAndFlush(...)` làm dữ liệu test được đẩy tới persistence context/database trước khi truy vấn; trong một số bài kiểm tra về constraint, flush đặc biệt cần thiết để lỗi xuất hiện đúng điểm quan sát.
- Theo cấu hình thông thường, `@DataJpaTest` chạy mỗi test trong transaction rồi rollback, giúp hạn chế rò rỉ dữ liệu giữa các ca. Nó cũng thường dùng embedded test database nếu cấu hình và dependency cho phép.
- Assertions kiểm tra cả tình huống tìm thấy dữ liệu và không tìm thấy dữ liệu. Nếu adapter map sai field, test đầu tiên sẽ thất bại.

**Không suy rộng từ embedded database sang production database.** SQL dialect, index, constraint, native query và khả năng transaction có thể khác giữa H2 và PostgreSQL/MySQL/... Nếu hợp đồng adapter phụ thuộc vào đặc tính của database thật, cân nhắc dùng Testcontainers với đúng loại database. Với cấu hình test database phù hợp, có thể dùng `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` để không tự thay datasource đã cấu hình; sau đó cung cấp datasource bằng Testcontainers/`@ServiceConnection` hoặc cơ chế phù hợp với phiên bản Spring Boot. Cấu hình ấy thuộc kiểm thử tích hợp hạ tầng và cần cân bằng tốc độ CI.

### 4.4. Tránh hiểu sai về phạm vi của JPA slice

Test vừa viết xác nhận repository và adapter ánh xạ kết quả trong một môi trường database kiểm thử. Nó **chưa xác nhận** controller và JPA adapter có cùng tồn tại, được nối bean đúng, giao dịch qua application service vận hành đúng, hay các event được xuất bản và tiếp nhận như mong muốn. Những câu hỏi này cần `@ApplicationModuleTest` hoặc integration test phù hợp.

## 5. Ranh giới giữa slice test và kiểm thử Spring Modulith

Spring Modulith giúp tổ chức một ứng dụng Spring Boot thành các application module có API và giới hạn phụ thuộc rõ ràng. Các test cần phân chia theo **câu hỏi muốn xác minh**:

| Loại test | Câu hỏi chính | Khởi tạo Spring? | Ví dụ |
| --- | --- | --- | --- |
| Unit test thuần Java | Quy tắc nghiệp vụ có cho kết quả đúng? | Không | Tính tổng tiền/chiết khấu |
| Web slice | Endpoint map request/response đúng? | Có, MVC slice | `@WebMvcTest(OrderController.class)` |
| JPA slice | Entity/query/adapter JPA đúng? | Có, JPA slice | `@DataJpaTest` + `@Import` |
| Architecture verification | Module có phụ thuộc đúng hướng và tuân thủ API không? | Không cần khởi tạo toàn ứng dụng | `ApplicationModules.of(ShopApplication.class).verify()` |
| Module integration test | Các bean và tương tác trong module hoạt động đúng khi ghép Spring? | Có, module context | `@ApplicationModuleTest` |
| End-to-end/integration | Request đi từ đầu vào qua database/event ngoài đời thực có đúng? | Có, có thể cần hạ tầng | `@SpringBootTest` và các test chuyên biệt |

Ví dụ kiểm tra kiến trúc riêng biệt:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {

    @Test
    void modules_follow_architecture_rules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Bài kiểm tra trên xác minh cấu trúc và phụ thuộc module theo các quy tắc Spring Modulith áp dụng, nhưng **không** kiểm tra JSON của endpoint hoặc SQL mapping. Hai slice test ở trên cũng có thể xanh dù một module khác lỡ tham chiếu trực tiếp đến `ordering.internal.persistence.OrderJpaEntity`. Vì vậy architecture verification phải là bài kiểm tra độc lập trong quality gate.

`@ApplicationModuleTest` thường dùng khi cần khởi tạo phạm vi Spring của một application module để kiểm chứng wiring, tác vụ ứng dụng, transaction, tương tác qua sự kiện và integration với thành phần thật/được thay thế theo cấu hình. Đây không phải bản thay thế mặc định cho slice test: khi chỉ cần assert HTTP mapping hoặc repository query, slice test cho lỗi dễ xác định hơn và ít thành phần chuyển động hơn.

### Khi nào cần nâng cấp từ slice test?

- Controller hoạt động trong `@WebMvcTest` nhưng lỗi ở bean mapping, security filter, transaction hoặc dependency khi lắp ứng dụng thật.
- JPA query hoạt động với database kiểm thử nhưng sai SQL dialect hoặc schema production.
- Sự kiện domain được publish nhưng listener nằm ở module khác, cần kiểm chứng việc giao nhận, transaction boundary hoặc event publication registry.
- Một adapter được cấu hình conditionally qua profile/bean factory và chỉ xuất hiện trong runtime integration context.
- Cần kiểm chứng một đường đi ứng dụng kết hợp **nhiều adapter** với nhau.

Khi đó, dùng `@ApplicationModuleTest` hoặc bài integration test có phạm vi và dependency phù hợp; đừng mở rộng bừa một slice thành toàn bộ ứng dụng.

## 6. Thiết kế slice test chất lượng

### 6.1. Xác định hợp đồng quan sát được

Với **web adapter**, kiểm tra method/path, status, body JSON, validation, authentication/authorization và định dạng lỗi theo hợp đồng API.

Với **persistence adapter**, kiểm tra tiêu chí truy vấn, map entity↔domain, xử lý null/không có dữ liệu, unique constraint, sắp xếp/phân trang và các tình huống transaction khi thuộc phạm vi test.

Với **outbound HTTP adapter**, kiểm tra URL, HTTP verb, header, request body, timeout/error mapping và phản hồi của dịch vụ qua mock server. Tránh gọi network thật ở slice test nếu không có lý do rõ ràng.

### 6.2. Cô lập dependency ở đúng biên

Ở web slice, `OrderQuery` được mock vì mục tiêu là kiểm tra cách controller gọi port và xây response. Nếu mock cả `OrderController`, test sẽ không còn kiểm tra adapter.

Ở JPA slice, repository và JPA thực sự được nạp để kiểm tra query. Nếu mock `OrderJpaRepository`, ta chỉ còn test một phép chuyển đổi đơn giản của `JpaOrderQuery` và bỏ qua hành vi quan trọng của persistence adapter.

Quy tắc chọn dependency:

- **Giữ thật** thành phần quyết định giá trị của slice: Spring MVC trong web slice; entity mapping và repository trong JPA slice.
- **Thay thế** dependency ngoài slice: application service/port của web test, HTTP server bên ngoài của client test.
- **Import có chọn lọc** class không tự động được nạp nhưng trực tiếp cần cho hợp đồng adapter; tránh import cả cây cấu hình.

### 6.3. Viết test độc lập và dễ xác định lỗi

- Dữ liệu đầu vào, ID, URL và expected values nên rõ ràng trong từng test.
- Không phụ thuộc thứ tự chạy, dữ liệu được tạo từ test khác hoặc đồng hồ hệ thống.
- Chọn tên test theo hành vi: `returns_404_when_order_does_not_exist` giúp người sửa hiểu hợp đồng bị phá vỡ.
- Với constraint JPA, chủ động flush trước assertion về exception để không đợi lỗi xuất hiện lúc transaction kết thúc.
- Khi có bất đồng giữa fake/mock và hệ thống thật, bổ sung module/integration test ở điểm nối tương ứng.

## 7. Trục trặc phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` ở `@WebMvcTest` | Controller phụ thuộc service/port không nằm trong MVC slice | Cung cấp `@MockitoBean`, test configuration hoặc import bean thật khi có chủ đích |
| `401`/`403` thay vì `200` | Security filter đang hoạt động | Cấu hình authentication/roles/CSRF theo contract |
| `NoSuchBeanDefinitionException` với adapter ở `@DataJpaTest` | Class `@Repository` implementation không được scan trong JPA slice | Dùng `@Import(Adapter.class)` |
| Test JPA chạy H2 xanh nhưng production lỗi | Khác dialect, schema, native SQL, constraints | Kiểm thử thêm bằng database tương ứng, có thể qua Testcontainers |
| `LazyInitializationException` ngoài slice | Truy cập lazy relation ngoài transaction thực tế | Kiểm tra transaction design và nâng lên integration test |
| Test web xanh nhưng module vi phạm quy tắc phụ thuộc | Slice test không xác minh module graph | Chạy `ApplicationModules.verify()` riêng |
| Test chậm do khởi động quá nhiều context | Dùng `@SpringBootTest` không cần thiết hoặc tạo context khác nhau không kiểm soát | Chọn slice nhỏ nhất đáp ứng mục tiêu; hạn chế cấu hình test khác nhau vô cớ |

Các lỗi trên là gợi ý chẩn đoán, không phải kết luận tự động. Hãy đọc exception và test configuration thực tế trước khi sửa code ứng dụng.

## 8. CI và quality gate

Với mục tiêu **ngăn phụ thuộc sai và hồi quy**, một pipeline hữu ích nên có nhiều lớp kiểm tra. Có thể tổ chức theo mức độ nhanh và mức độ cần hạ tầng:

1. **Unit tests:** chạy logic Java thuần, cực nhanh, không cần Spring.
2. **Slice tests:** chạy MVC, JPA, JSON và outbound-client adapter trong context hẹp.
3. **Architecture verification:** bắt vi phạm ranh giới module, phụ thuộc không được phép hoặc vòng phụ thuộc.
4. **Module/integration tests:** xác minh wiring của module, transaction, database thật và luồng sự kiện quan trọng.

Trong Gradle/Maven, các lớp test thông thường dưới `src/test/java` có thể cùng chạy bằng task `test`/goal `test`; nếu phân chia test suite hoặc CI job, phải cấu hình các bước bắt buộc sao cho không bỏ sót kiểm tra kiến trúc và test adapter. Kết quả test xanh là điều kiện của quality gate, còn độ bao phủ phụ thuộc vào các hợp đồng được thể hiện trong test.

Không nên tối ưu bằng cách tắt hàng loạt integration test; hãy dùng slice test để tăng tốc vòng phản hồi của adapter, rồi giữ số lượng module/integration test **đủ để xác minh những tương tác không xuất hiện trong slice**.

## 9. Bài tập thực hành

### Bài 1 — Web adapter

Mở rộng `OrderController` với endpoint `GET /api/orders?customerId=...`. Định nghĩa port tương ứng và viết `@WebMvcTest` kiểm tra:

- Request có `customerId` hợp lệ trả danh sách theo JSON contract.
- Request thiếu `customerId` được xử lý đúng theo quy định API.
- Controller truyền đúng tham số tới port và phản hồi không vô tình lộ field của JPA entity.

### Bài 2 — Persistence adapter

Bổ sung một truy vấn repository tìm đơn theo `customerId`, sắp xếp theo ID bên ngoài. Viết `@DataJpaTest` với ít nhất ba bản ghi để xác minh thứ tự, tính đầy đủ dữ liệu và tình huống không tìm thấy. Nếu dùng native SQL hoặc constraint phụ thuộc database, chạy thêm một biến thể với database cùng loại production.

### Bài 3 — Chọn loại test

Với mỗi yêu cầu sau, chỉ rõ test nhỏ nhất đủ phát hiện lỗi:

1. Controller trả `200` thay vì `404` khi không có đơn hàng.
2. Adapter map nhầm `customerId` sang `id`.
3. Module `payment` import class `ordering.internal.persistence.OrderJpaEntity`.
4. Khi lưu đơn, một sự kiện được xuất bản và module khác tiếp nhận sau transaction commit.

**Đáp án gợi ý:** (1) web slice; (2) JPA slice cho adapter dữ liệu, hoặc web slice nếu lỗi nằm trong response mapper; (3) architecture verification; (4) module/integration test cho event và transaction.

## 10. Ghi nhớ

**Slice test kiểm chứng hợp đồng của một adapter trong môi trường Spring được thu hẹp.** `@WebMvcTest` phù hợp để kiểm tra HTTP mapping, còn `@DataJpaTest` phù hợp để kiểm tra JPA mapping/truy vấn cùng phần adapter được import. Hãy giữ thật thành phần tạo ra hành vi cần kiểm chứng, thay thế những dependency nằm ngoài lát cắt và viết assertions về hợp đồng quan sát được.

Trong Spring Modulith, chất lượng module còn phụ thuộc vào **quy tắc ranh giới**, **wiring**, **database**, **event** và giao tiếp giữa module. Vì vậy, kết hợp slice test với `ApplicationModules.verify()`, `@ApplicationModuleTest` và các integration test cần thiết trong CI để chặn cả lỗi adapter lẫn vi phạm kiến trúc.
