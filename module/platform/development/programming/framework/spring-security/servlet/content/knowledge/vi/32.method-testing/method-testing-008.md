# Kiểm thử `@PreFilter`, `@PostFilter` và dữ liệu không thuộc quyền sở hữu — Spring Security Servlet

## 1. Mục tiêu

Một hệ thống nhiều người dùng thường chứa dữ liệu của **Alice, Bob** và nhiều tenant trong cùng database. Chỉ kiểm tra `authenticated()` ở HTTP endpoint là chưa đủ: một người dùng đã đăng nhập vẫn có thể yêu cầu bản ghi thuộc người khác bằng cách sửa ID trên URL hoặc trong danh sách gửi lên API. Đây là nhóm lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

Trong **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**, method security có các annotation liên quan:

- **`@PreFilter`**: lọc từng phần tử của một đối số dạng collection trước khi method thực thi.
- **`@PostFilter`**: lọc từng phần tử của kết quả collection sau khi method thực thi nhưng trước khi kết quả được trả cho caller.
- **`@PreAuthorize`**: quyết định cho phép hoặc từ chối **toàn bộ method invocation** trước khi chạy.
- **`@PostAuthorize`**: kiểm tra sau khi chạy method (thường dùng với một object trả về, cần hiểu rủi ro side effect).

Mục tiêu bài học là **hiểu chính xác khi nào một phần tử bị loại bỏ âm thầm, khi nào cả thao tác phải bị từ chối, cách viết tests để không lộ record của chủ sở hữu khác, và những giới hạn của filtering khi bảo vệ dữ liệu thực**.

Kết thúc bài, bạn sẽ làm được:

1. Dựng một project Spring Security Servlet có `@EnableMethodSecurity`.
2. Dùng `filterObject` và `authentication.name` trong SpEL để xử lý collection.
3. Phân biệt dữ liệu **đến từ client** với dữ liệu **được lấy từ repository đã tin cậy**.
4. Dùng JUnit 5, `@WithMockUser`, MockMvc và assertions để thử các tình huống Alice/Bob, không có quyền, object không tồn tại.
5. Nhận diện tình huống **không nên** dùng `@PreFilter` hoặc `@PostFilter` để thay thế quyền sở hữu ở tầng persistence/service.

Phần ví dụ Java dùng **dữ liệu in-memory để học rõ annotation**. Trong production, phải có kiểm tra quyền ở nơi truy vấn/cập nhật database, tenant isolation, transactional integrity và audit phù hợp.

## 2. Cơ chế method security và điểm thực thi của filter

Spring Security bảo vệ method thông qua interceptors/advisors trong Spring AOP. Với cấu hình phổ biến:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` ở Spring Security 6 bật hỗ trợ `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` theo mặc định (`prePostEnabled=true`), trừ khi ứng dụng thay đổi tùy chọn. Với Spring Security phiên bản cũ hơn, cơ chế và cú pháp bật global method security có thể khác.

Luồng tổng quát:

```text
HTTP request -> Spring Security filter chain xác thực principal
    -> Controller gọi Spring-managed Service bean thông qua proxy
        -> @PreAuthorize kiểm tra quyền gọi method
        -> @PreFilter lọc collection đầu vào (nếu có)
        -> Business method thực thi
        -> @PostFilter lọc collection đầu ra (nếu có)
        -> @PostAuthorize kiểm tra điều kiện kết quả (nếu có)
    -> Controller gửi response
```

Sơ đồ là **cách hiểu khái niệm**, không bảo đảm thứ tự cố định giữa tất cả advice nếu bạn gắn nhiều annotation lên cùng method hoặc tùy biến advisor ordering. Khi phối hợp nhiều annotation, phải test đúng filter chain và method thật thay vì suy ra thứ tự từ sơ đồ.

`SecurityContextHolder` chứa `Authentication` của request; method security lấy authentication từ context hiện hành. `authentication.name` thường là tên principal, nhưng trong JWT/OIDC hoặc custom principal nó có thể là subject/identifier khác username giao diện. Hãy xác định một **định danh ổn định đáng tin cậy** cho chính sách owner.

**Quan trọng:** Spring AOP proxy chỉ chặn các lời gọi đi qua proxy. Nếu bạn viết `this.visibleOrders()` trong chính service chứa method được annotate, hoặc `new OrderService(...)` bằng tay thay cho Spring bean, security advice có thể bị bỏ qua. Đây là lý do tests phải lấy service qua ApplicationContext.

## 3. `@PreFilter` khác `@PostFilter` ra sao?

| Điểm so sánh | `@PreFilter` | `@PostFilter` |
| --- | --- | --- |
| Đối tượng bị lọc | Tham số truyền vào method | Giá trị method trả về |
| Thời điểm | Trước business logic | Sau khi business logic hoàn tất |
| Biểu thức từng phần tử | `filterObject` | `filterObject` |
| Ví dụ | Chỉ cho method nhận các ID có owner đúng | Chỉ trả về các bản ghi có owner đúng |
| Không khớp policy | Phần tử bị loại bỏ | Phần tử bị loại khỏi kết quả |
| Có tự ném 403 vì một phần tử sai? | **Không**, thông thường chỉ lọc | **Không**, thông thường chỉ lọc |
| Có tự ngăn query đọc dữ liệu người khác? | Không | Không — method có thể đã truy vấn hết |
| Phù hợp cho | Chọn tập được phép xử lý khi nghiệp vụ cho phép loại bớt | Demo/collection nhỏ, lọc kết quả cần hiển thị |
| Khi cần thao tác nguyên tử và phải từ chối tất cả | Dùng `@PreAuthorize`/guard khác | Không đủ |

### 3.1. `filterObject` và `filterTarget`

Khi filter đánh giá một collection, mỗi phần tử lần lượt được gán vào biến SpEL **`filterObject`**.

```java
@PreFilter("filterObject.owner() == authentication.name")
public List<OrderView> keepOnlyOwned(List<OrderView> orders) {
    return List.copyOf(orders);
}
```

Ví dụ trên *minh họa biểu thức*, chưa phải class tự chạy. **Nếu collection chứa đối tượng do client tự tạo có field `owner`, field đó không phải bằng chứng quyền sở hữu**. Một client có thể tự khai `owner="alice"` cho ID của Bob. Không dùng nguyên ví dụ này làm authorization của một thao tác ghi thật.

Nếu method có nhiều đối số có thể được lọc, khai báo **`filterTarget`** để chọn chính xác tham số:

```java
@PreFilter(
    filterTarget = "ids",
    value = "@ownershipPolicy.isOwner(filterObject, authentication.name)"
)
public List<Long> keepOwnedIds(List<Long> ids) {
    return List.copyOf(ids);
}
```

Ở đây hàm `ownershipPolicy.isOwner(id, username)` **đọc quyền sở hữu thật từ repository/server**, không tin trường `owner` do client gửi. `filterObject` là một ID `Long`. Để expression gọi được helper, `ownershipPolicy` phải là Spring bean và helper method phải truy cập được.

### 3.2. `@PostFilter` dùng trên kết quả collection

```java
@PostFilter("filterObject.owner() == authentication.name")
public List<OrderView> visibleOrders() {
    return new ArrayList<>(repository.findAll());
}
```

Method lấy data từ server trước rồi Spring Security lọc kết quả. Trong ví dụ học tập, `repository.findAll()` trả một tập rất nhỏ và method trả **mutable list**. Tránh trả một `List.of(...)` bất biến nếu framework/filter cần loại phần tử khỏi collection; với kiểu `Page<T>` hoặc reactive publisher, đừng tự coi đó là collection có thể áp dụng annotation tương tự.

**`@PostFilter` không phải cơ chế tối ưu cho bảng lớn**: toàn bộ object có thể đã được truy xuất, serialize nội bộ, ghi log, hoặc chạm vào bộ nhớ trước khi bị loại khỏi return value. Khi phân trang, việc lọc sau query còn khiến số bản ghi và tổng số bản ghi khó nhất quán. Trong production, nên lọc theo owner/tenant **ngay trong repository query**.

### 3.3. Trả về object đơn lẻ thì sao?

Với một đơn hàng `GET /orders/{id}`, `@PostFilter` không phải lựa chọn đúng vì method trả `OrderView`, không phải collection. Có thể dùng:

```java
@PostAuthorize("returnObject.owner() == authentication.name")
public OrderView getOne(long id) {
    return repository.getById(id);
}
```

Đây là **đoạn minh họa**, không phải implementation đầy đủ. `@PostAuthorize` chặn việc trả object nếu điều kiện sai, nhưng business method **đã chạy**; không dùng kiểu này để bảo vệ các side effect nhạy cảm như chuyển tiền, duyệt đơn hay xóa dữ liệu. Với thao tác theo ID, dùng **`@PreAuthorize` + kiểm tra owner từ repository** trước khi thực hiện hành động, hoặc một policy guard tường minh có transaction.

## 4. Dữ liệu không thuộc quyền sở hữu: những tình huống phải thử

Giả sử repository có:

| ID | Owner | Tenant | Title |
| --- | --- | --- | --- |
| 1 | alice | team-a | Đơn A1 |
| 2 | bob | team-b | Đơn B1 |
| 3 | alice | team-a | Đơn A2 |

Tác nhân đang đăng nhập là **alice**. Kỳ vọng:

- `visibleOrders()` chỉ trả ID **1, 3**; ID 2 không được lộ ở response.
- `keepOwnedIds([1,2,3])` truyền vào business method tập **[1,3]**.
- Nếu hợp đồng API là **“thực hiện toàn bộ hoặc từ chối”**, `requireAllOwned([1,2,3])` phải ném `AccessDeniedException`/trả 403, **không âm thầm thực hiện [1,3]**.
- `getOwnedById(2)` phải bị từ chối trước khi service trả record Bob.
- Nếu request khai giả `owner=alice` nhưng `id=2`, policy vẫn kiểm tra owner từ database và từ chối.
- Khi Bob đăng nhập, các kết quả đảo chiều: Bob chỉ được nhìn thấy ID **2**.
- Với dữ liệu không tồn tại, policy fail-closed; việc trả 403 hay 404 phải theo thiết kế chống dò tồn tại ID.
- Với multi-tenant, `owner` đơn thuần chưa chắc đủ: một user name có thể trùng giữa tenant hoặc cùng người có quyền khác nhau ở từng tổ chức. Cần kiểm tra **owner + tenant + resource relationship**.

**Bản ghi do client gửi lên không phải sự thật về quyền sở hữu.** Không tin `owner`, `tenantId`, `role`, `isAdmin`, `approvedBy` từ request body hoặc query string; server phải xác minh các thuộc tính này bằng dữ liệu được bảo vệ.

## 5. Ví dụ Spring Boot 3.x chạy được: các lớp cần tạo

Tạo project bằng Spring Initializr, chọn Java 17+, Spring Boot 3.x, Gradle (Groovy) và các starters: Spring Web, Spring Security. Cấu trúc source trong ví dụ:

```text
src/main/java/com/example/ownership/
  OwnershipApplication.java
  SecurityConfig.java
  OrderView.java
  OrderRepository.java
  OwnershipPolicy.java
  OrderService.java
  OrderController.java

src/test/java/com/example/ownership/
  OwnershipMethodSecurityTests.java
```

Trong `build.gradle` (phần dependency; plugin/dependency management do Spring Initializr tạo):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đoạn project này cố ý dùng `List` in-memory để test hành vi của Spring AOP mà không cần dựng DB, migration hoặc JPA. **Không coi đây là mẫu production cho quản lý đơn hàng**: dịch vụ thật nên có database-level ownership/tenant policy và concurrency control.

### 5.1. Application entrypoint

Tập tin `src/main/java/com/example/ownership/OwnershipApplication.java`:

```java
package com.example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
```

### 5.2. Model với Java `record`

Tập tin `src/main/java/com/example/ownership/OrderView.java`:

```java
package com.example.ownership;

public record OrderView(
    long id,
    String owner,
    String tenantId,
    String title
) {
}
```

Record là một view bất biến dùng để trình bày; ownership thực tế của resource phải đến từ nguồn dữ liệu tin cậy.

### 5.3. Repository in-memory, trả bản sao mutable

Tập tin `src/main/java/com/example/ownership/OrderRepository.java`:

```java
package com.example.ownership;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final List<OrderView> data = List.of(
        new OrderView(1L, "alice", "team-a", "Đơn A1"),
        new OrderView(2L, "bob", "team-b", "Đơn B1"),
        new OrderView(3L, "alice", "team-a", "Đơn A2")
    );

    public List<OrderView> findAll() {
        return new ArrayList<>(data);
    }

    public Optional<OrderView> findById(long id) {
        return data.stream().filter(order -> order.id() == id).findFirst();
    }
}
```

`List.of(...)` trong field `data` là immutable, nhưng **`findAll()` trả `ArrayList` riêng** để `@PostFilter` có thể lọc collection mà không tác động vào danh sách gốc. Trả trực tiếp một collection được quản lý bởi ORM rồi để filter xóa phần tử có thể tạo side effects ngoài ý muốn; với production phải chọn chiến lược lọc tại query.

### 5.4. Policy bean: kiểm tra ID bằng sự thật ở repository

Tập tin `src/main/java/com/example/ownership/OwnershipPolicy.java`:

```java
package com.example.ownership;

import java.util.List;

import org.springframework.stereotype.Component;

@Component("ownershipPolicy")
public class OwnershipPolicy {

    private final OrderRepository repository;

    public OwnershipPolicy(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(Long id, String username) {
        if (id == null || username == null) {
            return false;
        }

        return repository.findById(id)
            .map(order -> username.equals(order.owner()))
            .orElse(false);
    }

    public boolean allOwned(List<Long> ids, String username) {
        return ids != null
            && !ids.isEmpty()
            && ids.stream().allMatch(id -> isOwner(id, username));
    }
}
```

- `isOwner` tra cứu record **trên server**, không so với field owner do client tự gửi.
- ID thiếu, không tồn tại hoặc username thiếu đều **false**.
- `allOwned` yêu cầu **mọi** ID hợp lệ; không có logic “cho qua những ID thuộc quyền”.
- Nếu production có tenant, method phải nhận **tenant đáng tin cậy** và kiểm tra trong truy vấn owner/tenant. `username` chỉ đủ cho ví dụ một tập người dùng nhỏ.
- Nếu một ID được cấp phép rồi resource bị đổi owner trước khi thao tác, phải thiết kế transaction, versioning hoặc query có `WHERE owner_id = ...` để tránh **TOCTOU (time-of-check/time-of-use)**.

Mẫu trên đọc repository từng ID; với danh sách lớn sẽ tốn N queries. Ở production, thay bằng query tập hợp/joins, policy guard kiểm tra số lượng được phép và cập nhật có điều kiện.

### 5.5. Service áp dụng ba chính sách khác nhau

Tập tin `src/main/java/com/example/ownership/OrderService.java`:

```java
package com.example.ownership;

import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    // Trước khi gọi method: chỉ đưa ID thật sự thuộc caller vào method.
    @PreFilter(
        filterTarget = "ids",
        value = "@ownershipPolicy.isOwner(filterObject, authentication.name)"
    )
    public List<Long> keepOwnedIds(List<Long> ids) {
        return List.copyOf(ids);
    }

    // Sau khi method trả kết quả: chỉ hiển thị record thuộc caller.
    @PostFilter("filterObject.owner() == authentication.name")
    public List<OrderView> visibleOrders() {
        return new ArrayList<>(repository.findAll());
    }

    // Hợp đồng nguyên tử: bất kỳ ID nào không thuộc caller => từ chối.
    @PreAuthorize(
        "@ownershipPolicy.allOwned(#p0, authentication.name)"
    )
    public List<Long> requireAllOwned(List<Long> ids) {
        return List.copyOf(ids);
    }

    // Tài nguyên đơn lẻ: kiểm tra quyền với ID trước khi đọc để trả ra.
    @PreAuthorize(
        "@ownershipPolicy.isOwner(#p0, authentication.name)"
    )
    public OrderView getOwnedById(long id) {
        return repository.findById(id)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
```

**Điểm quan trọng về `@PreFilter`:** Service nhận collection **đã bị lọc**. Nếu API ngầm yêu cầu xử lý tất cả item trong batch, đây có thể là hành vi sai về nghiệp vụ: user tưởng cả batch đã được xử lý nhưng một số item bị bỏ qua. Vì vậy `requireAllOwned` sử dụng `@PreAuthorize` để từ chối tất cả khi có bất kỳ ID không thuộc user.

**Điểm quan trọng về `@PostFilter`:** `visibleOrders()` vẫn gọi `findAll()` trước khi lọc. Đây là demo của annotation, **không phải khuyến nghị truy vấn tất cả đơn hàng rồi lọc trong JVM**. Service cũng không được tạo side effects, log dữ liệu bí mật hoặc gửi thông báo chứa record của Bob trong lúc đọc trước khi PostFilter chạy.

**Điểm quan trọng về `#p0`:** Biểu thức này tham chiếu đối số thứ nhất theo **vị trí**, không phụ thuộc việc Java class có lưu parameter names qua compiler. Khi nhiều tham số và muốn tên rõ nghĩa, có thể dùng cơ chế parameter-name discovery hoặc annotation hỗ trợ của Spring Security, nhưng phải test với build thật.

### 5.6. Bật method security và xác thực HTTP

Tập tin `src/main/java/com/example/ownership/SecurityConfig.java`:

```java
package com.example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Ở đây `authenticated()` chỉ yêu cầu caller đã đăng nhập ở HTTP layer; **ownership được kiểm tra trong `OrderService`**. Ví dụ dùng Basic Auth vì đơn giản, nhưng **không tắt CSRF** mặc định. Spring Security vẫn bảo vệ những thao tác thay đổi trạng thái trong ngữ cảnh browser phù hợp; demo HTTP chỉ có GET nên không cần token CSRF. Trong production, cấu hình session, Basic/Bearer, CSRF, CORS và logging phải phù hợp ứng dụng thực tế.

### 5.7. Controller gọi Spring-managed service

Tập tin `src/main/java/com/example/ownership/OrderController.java`:

```java
package com.example.ownership;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    public List<OrderView> list() {
        return orders.visibleOrders();
    }

    @GetMapping("/api/orders/{id}")
    public OrderView one(@PathVariable long id) {
        return orders.getOwnedById(id);
    }
}
```

Controller gọi bean `OrderService` đã được Spring inject, nên lời gọi đi qua method-security proxy và annotations được thực thi. **Không gọi `new OrderService(...)` hoặc `this.visibleOrders()` để đi vòng quanh proxy.**

Các API GET này không nhận `owner` từ query parameter để chọn dữ liệu hiển thị; chỉ dựa trên principal đã được xác thực và server-side policy.

## 6. Kiểm thử thật bằng JUnit 5 + `@WithMockUser`

Tập tin **`src/test/java/com/example/ownership/OwnershipMethodSecurityTests.java`**:

```java
package com.example.ownership;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipMethodSecurityTests {

    @Autowired
    OrderService service;

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void postFilterReturnsOnlyAliceOrders() {
        List<Long> ids = service.visibleOrders().stream()
            .map(OrderView::id).toList();

        assertEquals(List.of(1L, 3L), ids);
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilterReturnsOnlyBobOrder() {
        List<Long> ids = service.visibleOrders().stream()
            .map(OrderView::id).toList();

        assertEquals(List.of(2L), ids);
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilterRemovesForeignIdsBeforeMethodRuns() {
        // PHẢI dùng collection mutable cho filter ở ví dụ này.
        List<Long> mixed = new ArrayList<>(List.of(1L, 2L, 3L));

        List<Long> result = service.keepOwnedIds(mixed);

        assertEquals(List.of(1L, 3L), result);
    }

    @Test
    @WithMockUser(username = "alice")
    void strictBatchRejectsEvenOneForeignId() {
        assertThrows(AccessDeniedException.class,
            () -> service.requireAllOwned(List.of(1L, 2L, 3L)));

        assertEquals(List.of(1L, 3L),
            service.requireAllOwned(List.of(1L, 3L)));
    }

    @Test
    @WithMockUser(username = "alice")
    void singleForeignRecordDeniedBeforeServiceReturnsIt() {
        assertThrows(AccessDeniedException.class,
            () -> service.getOwnedById(2L));

        assertEquals(1L, service.getOwnedById(1L).id());
    }

    @Test
    void mvcListNeverSerializesForeignOrder() throws Exception {
        mvc.perform(get("/api/orders").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[*].id",
                containsInAnyOrder(1, 3)));

        mvc.perform(get("/api/orders").with(user("bob")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(2));
    }

    @Test
    void mvcSingleResourceEnforcesOwner() throws Exception {
        mvc.perform(get("/api/orders/2").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders/2").with(user("bob")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void unauthenticatedCallerCannotListOrders() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
```

### 6.1. Test này chứng minh được điều gì?

- Các lời gọi `service` được thực hiện qua **Spring bean đã proxied**, không phải object tự tạo.
- `@WithMockUser(username = "alice")` đặt Authentication giả trên test thread để `authentication.name` trong SpEL có giá trị đúng.
- `@PreFilter` nhận một `ArrayList` mutable và loại ID Bob trước khi service xử lý.
- `@PostFilter` giới hạn kết quả theo principal Alice/Bob, không đưa record ID 2 vào response Alice.
- `@PreAuthorize` dùng làm **strict guard**, không cho phép batch có một phần tử không thuộc owner.
- MockMvc kiểm tra kết quả **HTTP** và 403 trên ID thuộc người khác, thay vì chỉ đọc return value của service.
- Không có credentials phải nhận 401 trong cấu hình Basic Auth minh họa; token/session thực tế của hệ thống có thể có entry point khác.

Test dùng **in-memory repository và mock security principal**, chưa xác minh token JWT, session login thực hoặc database query. Với ứng dụng dùng JWT, bổ sung test Resource Server (`JwtDecoder`, issuer/audience, subject mapping) tương ứng; `@WithMockUser` không tự chứng minh JWT claims đã được xác minh.

### 6.2. Chạy test và dự đoán kết quả

Trong project Gradle Wrapper do Spring Initializr tạo:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Kỳ vọng:** các test ở mục 6 đều pass nếu project và dependency đúng, và method security thực sự được bật. Không ghi chính xác số dòng log/BUILD SUCCESSFUL như một stdout cố định, vì Gradle version, logging và plugins có thể khác nhau.

Khi chạy ứng dụng với:

```bash
./gradlew bootRun
```

Bạn cần cấu hình tài khoản test/Identity Provider thật nếu muốn gọi HTTP Basic ngoài MockMvc; Spring Boot Security có thể tạo một user mặc định với generated password ở development. **Không dùng generated password của console làm cơ chế auth production**, và không để sample ID 1–3 thay cho dữ liệu database thật.

## 7. Vì sao test `@PreFilter` có thể pass nhưng authorization vẫn sai?

### 7.1. Client có thể sửa trường owner

Cách dùng sai thường gặp:

```java
@PreFilter("filterObject.owner() == authentication.name")
public void approveOrders(List<OrderDto> submittedOrders) {
    // Dùng các record DTO từ client để quyết định phê duyệt.
}
```

**Đoạn code chỉ để minh họa anti-pattern**, không có định nghĩa đầy đủ `OrderDto` và không nên triển khai thật. Nếu Alice gửi một DTO của đơn hàng Bob nhưng đặt `owner="alice"`, filter coi object là của Alice. Vì vậy ví dụ runnable ở mục 5 **nhận ID rồi tra repository server-side**, không tin `owner` do request cung cấp.

Đối với thao tác duyệt đơn, API production nên lấy entity thật theo ID, kiểm tra principal/tenant/role/ownership từ nguồn tin cậy, rồi cập nhật trong transaction. Với cập nhật có tranh chấp, kiểm tra quyền và update theo điều kiện (ví dụ owner_id/tenant_id) có thể an toàn hơn hai bước query rồi update rời rạc.

### 7.2. Silent filtering có thể vi phạm yêu cầu nghiệp vụ

Nếu người dùng gửi `[1,2,3]` để thực hiện một batch operation và app silently drop ID 2, caller có thể hiểu nhầm là cả ba đã được xử lý. Dù không leak data, đây có thể là **business integrity bug**. Chọn một hợp đồng rõ:

- **Partial allowed:** chỉ xử lý ID hợp lệ, response có số lượng/mapping phù hợp, audit các phần tử bị bỏ qua mà không lộ dữ liệu nhạy cảm.
- **Atomic reject:** nếu một ID không được phép, trả 403/exception và **không thao tác phần tử nào**; dùng `@PreAuthorize` hoặc policy guard trước khi mutate data.
- **Per-item errors:** trả trạng thái theo item khi sản phẩm thật sự yêu cầu, nhưng không làm lộ owner/title của item không thuộc user.

`@PreFilter` tự nó **không** bảo đảm atomicity và cũng không quyết định response code theo hợp đồng sản phẩm.

### 7.3. Post-filtering vẫn có thể lộ qua side effects

Mã xấu:

```java
@PostFilter("filterObject.owner() == authentication.name")
public List<OrderView> visible() {
    List<OrderView> all = repository.findAll();
    sendNotificationsFor(all); // Side effect đã chạy trước khi lọc!
    return all;
}
```

Ví dụ này là **anti-pattern minh họa**, không phải class chạy độc lập. `@PostFilter` lọc **giá trị trả về**, không thể hoàn tác side effects trước đó. Nếu method log body, gọi API bên thứ ba hoặc ghi dữ liệu theo tập `all`, thông tin không được phép đã có thể bị tiết lộ trước khi annotation thực thi.

**Nguyên tắc:** dùng repository query đã hạn chế theo principal/tenant ngay từ đầu, và dùng service policy để xác minh quyền tại từng hành động. `@PostFilter` là lớp defense-in-depth hoặc công cụ hữu ích cho collection nhỏ, không phải ranh giới dữ liệu duy nhất.

### 7.4. `Page<T>` và kết quả lớn

`Page<OrderView>` có metadata `totalElements`, `totalPages`, sorting và offsets. Nếu chỉ lọc nội dung sau query, page size và tổng số record có thể tiết lộ dữ liệu của tenant khác hoặc không còn khớp thực tế; `@PostFilter` cũng không được coi là hỗ trợ mọi kiểu wrapper trả về.

Với pagination, đặt điều kiện owner/tenant trong **SQL/JPQL/Specification**:

```sql
SELECT id, owner_id, tenant_id, title
FROM orders
WHERE owner_id = :authenticated_owner
  AND tenant_id = :authenticated_tenant
ORDER BY id
LIMIT :page_size OFFSET :offset;
```

Đây là ví dụ SQL tổng quát về phạm vi kết quả, không phải query đã chống mọi vấn đề phân quyền. Tham số phải được bind an toàn; `authenticated_owner` và `authenticated_tenant` được lấy từ authentication/policy của server, **không lấy trực tiếp từ client**. Đếm `COUNT(*)` cũng cần điều kiện tương đương.

### 7.5. Quyền sở hữu có thể khác creator

Không phải hệ thống nào cũng dùng `resource.owner == principal.name`. Một tài liệu có thể được chia sẻ nhóm, một account có delegate quyền, hoặc tài nguyên thuộc tổ chức thay vì cá nhân. Policy thực tế có thể xét:

- Owner ID, tenant ID và trạng thái resource.
- Role/permission trong tenant.
- ACL hoặc membership của nhóm sở hữu.
- Các quy tắc chuyển giao quyền, phê duyệt hoặc thời hạn ủy quyền.
- Danh tính của **service account** và phạm vi ủy nhiệm cụ thể.

Nếu quyền phụ thuộc nhiều nguồn, hãy đưa vào một service/AuthorizationManager chuyên trách và test bằng ma trận principal × resource × action, thay vì viết SpEL dài khó audit trong từng annotation.

## 8. Thử nghiệm tiêu cực không thể bỏ qua

### 8.1. Ma trận chính sách tối thiểu

| Caller | Input | Phương thức | Kết quả mong đợi |
| --- | --- | --- | --- |
| alice | IDs [1,3] | `keepOwnedIds` | Giữ [1,3] |
| alice | IDs [1,2,3] | `keepOwnedIds` | Chỉ [1,3] (partial filtering) |
| alice | IDs [1,2,3] | `requireAllOwned` | Từ chối toàn bộ |
| alice | ID 2 | `getOwnedById` | AccessDenied/HTTP 403 |
| bob | ID 2 | `getOwnedById` | Được phép |
| bob | Danh sách toàn bộ | `visibleOrders` | Chỉ ID 2 |
| Chưa đăng nhập | GET /api/orders | HTTP | 401 trong cấu hình demo |
| alice | ID không tồn tại | `getOwnedById` | Từ chối theo policy fail-closed |
| alice ở tenant A | ID thuộc tenant B cùng username | Bảo vệ thực tế | Từ chối |
| alice | DTO giả `owner=alice`, ID thuộc Bob | Kiểm tra nguồn server | Không được cấp quyền |
| alice | List immutable chứa ID khác owner | `@PreFilter` | Kiểm tra contract/mutability, không bỏ qua filter |

### 8.2. Test fail nếu method security bị tắt

Một phép thử quan trọng trong pipeline CI là **test phải bị fail khi tắt `@EnableMethodSecurity`**. Khi không có advice, `visibleOrders()` có thể trả cả Bob, `keepOwnedIds` giữ ID 2 và `requireAllOwned` không ném exception.

Điều này giải thích tại sao chỉ dùng Mockito `new OrderService(mockRepository)` để test logic Java **không test được annotation**. Kiểm thử method security cần **Spring ApplicationContext** và bean proxy thật.

### 8.3. Self-invocation và phương thức không được proxied

```java
@Service
public class ExampleService {

    public void run() {
        // Gọi nội bộ: có thể không đi qua method-security proxy.
        visibleOrders();
    }

    @PostFilter("filterObject.owner() == authentication.name")
    public List<OrderView> visibleOrders() {
        return List.of();
    }
}
```

Đoạn này minh họa vấn đề proxy; nếu kết quả trả immutable list và filter phải remove, nó còn không phù hợp để chạy như ví dụ thật. Không dùng nó làm service mẫu; service hoàn chỉnh ở mục 5 trả `ArrayList`.

Khi bảo vệ business operation, đặt annotation trên **public method của Spring-managed bean được gọi từ bean khác**, và có tests chứng minh invocation đi qua advice. Với một số kiểu proxy/configuration, final/private method hoặc call nội bộ có thể không được intercept như mong muốn.

## 9. Test quyền ở HTTP khác test method

Ba cấp kiểm thử có mục tiêu khác nhau:

| Cấp | Ví dụ | Phát hiện được | Không chứng minh |
| --- | --- | --- | --- |
| Converter/Policy unit | `OwnershipPolicy.isOwner(2L,"alice")` | Logic đối chiếu owner theo repo | Spring AOP/advice có chạy |
| Method security integration | `@SpringBootTest`, `@WithMockUser`, gọi bean service | `@PreFilter`, `@PostFilter`, `@PreAuthorize` có hiệu lực trên method | Toàn bộ HTTP filters, cookie, JWT thực |
| HTTP integration | MockMvc + Spring Security | 401/403/200, mapping/serialization không lộ record | DB RLS, IdP token validation thực, production proxy |

Nếu dùng JWT Resource Server thay vì Basic demo, `@WithMockUser` đặt principal giả và không test signature/audience/claim mapping. Hãy bổ sung một số test với JWT được ký bởi test key hoặc fake `JwtDecoder` có kiểm soát, rồi test authorities/subject/tenant đúng format production. **`with(jwt())` có thể bỏ qua decoder thật** trong MockMvc; không hiểu sai một test pass là token signing đã được xác minh.

### 9.1. Test bảo vệ against cross-tenant

Nếu ứng dụng có nhiều tenant, chuẩn bị ít nhất hai record có cùng tên owner nhưng ở tenant khác nhau:

```text
id=41; owner=alex; tenant=tenant-a
id=42; owner=alex; tenant=tenant-b
```

Với caller `alex@tenant-a`, kỳ vọng chỉ thấy ID 41, không thấy ID 42. Cần chính sách xác định tenant **từ Authentication hợp lệ hoặc server-side membership**, không tin giá trị `tenant` từ header không xác thực. Ví dụ mẫu đơn giản ở mục 5 **chưa triển khai** kiểm tra tenant này; test cross-tenant là tiêu chí bắt buộc trước khi triển khai dịch vụ nhiều tenant thật.

### 9.2. Test dữ liệu thiếu hoặc bất thường

- Input có `null`, ID âm, ID không tồn tại, duplicate ID, danh sách rỗng.
- Client gửi `owner`, `role`, `tenantId` giả để thử bypass.
- Caller bị mất quyền giữa **check** và **update**.
- User bị khóa/thu hồi quyền nhưng session/token còn hiệu lực.
- Nhiều batch requests đồng thời truy cập cùng resource.
- Repository/query chỉ trả một subset, `@PostFilter` có còn đúng với pagination?
- Trường hợp filter loại toàn bộ kết quả: response là empty list hay 403 theo contract?
- `@PreFilter` với collection không thể mutate có gây exception? Nếu có, sửa kiểu dữ liệu/thiết kế, không vô hiệu method security.
- Một service method gọi nội bộ một service method được annotate: có bỏ qua proxy không?

Test negative case quan trọng hơn chỉ test “Alice thấy đơn của Alice” vì IDOR thường xuất hiện ở **ID thuộc người khác hoặc tenant khác**.

## 10. Thiết kế production: lọc trong SQL và bảo vệ update

Trong production, nên coi **query có điều kiện bảo mật** là tuyến phòng thủ chính cho danh sách/pagination:

```java
// Interface minh họa; cần Spring Data JPA, entity và mapping thực tế.
Page<OrderEntity> findByOwnerIdAndTenantId(
    String ownerId,
    String tenantId,
    Pageable pageable
);
```

Đây là **trích đoạn Spring Data repository**, không phải chương trình độc lập có thể biên dịch vì `OrderEntity`, `Pageable` thuộc project có Spring Data JPA. `ownerId` và `tenantId` phải lấy từ security principal/trusted membership.

Đối với update theo ID, có thể đặt điều kiện quyền trực tiếp ở câu SQL:

```sql
UPDATE orders
SET state = 'APPROVED'
WHERE id = :id
  AND owner_id = :authenticated_owner
  AND tenant_id = :authenticated_tenant
  AND state = 'PENDING';
```

Sau đó xem **affected row count**; nếu 0, trả lỗi phù hợp (không tồn tại, không được phép, hay trạng thái không hợp lệ theo contract). Cách này hỗ trợ kiểm soát race tốt hơn việc `SELECT` rồi `UPDATE` không ràng buộc owner. Với domain phức tạp, dùng transaction lock/version, database RLS hoặc `AuthorizationManager` theo policy tập trung.

`@PreFilter`/`@PostFilter` vẫn có vai trò trong kiểm thử và bảo vệ một số collection nhưng **không thay thế** data access control: một request có thể gọi endpoint khác, task bất đồng bộ hoặc repository trực tiếp. Giới hạn quyền nên được áp dụng ở **nhiều điểm cần thiết** (HTTP, service, DB) mà không dựa vào một annotation duy nhất.

## 11. Lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `@PreFilter` không lọc gì | Chưa bật `@EnableMethodSecurity`, lời gọi không đi qua proxy | Gọi Spring bean từ bean khác, test ApplicationContext |
| `@PostFilter` trả dữ liệu người khác | Phương thức không được proxied, biểu thức owner sai, thiếu annotation | Test trực tiếp method qua Spring bean và response MockMvc |
| Spring ném lỗi khi lọc list | Danh sách bất biến (`List.of`) hoặc collection không phù hợp | Dùng mutable collection ở ranh giới filter, hoặc lọc ở query |
| SpEL không tìm thấy bean `ownershipPolicy` | Thiếu `@Component` hoặc bean name khác | Đăng ký bean và kiểm tra tên trong expression |
| SpEL dùng `#ids` trả null | Thiếu tên parameter runtime/annotation hỗ trợ | Chỉ rõ `filterTarget`; dùng `#p0` cho positional method argument |
| Caller không có Authentication | Test chưa dùng `@WithMockUser`, request chưa xác thực | Setup SecurityContext đúng, không tắt advice |
| `@WithMockUser` test pass nhưng HTTP 403 | HTTP auth, CSRF, filter matcher hoặc JWT claims khác | Test bằng MockMvc với cấu hình filters đúng |
| Chỉ username đúng nhưng sai tenant | Policy chưa giới hạn tenant | Lấy tenant tin cậy và kiểm tra row-level |
| User giả owner trong JSON để đọc/sửa record | Policy tin DTO client thay vì repository | Xác minh ID, owner, tenant trên server |
| Partial batch lặng lẽ bỏ item | `@PreFilter` được dùng cho nghiệp vụ atomic | Dùng `@PreAuthorize` `allOwned` hoặc fail-fast service guard |
| Trả `Page` với tổng số dữ liệu sai | Lọc sau query thay vì theo WHERE | Lọc trong repository và count query tương ứng |
| `@PostFilter` không chặn side effect | Method đã chạy trước khi output được lọc | Bảo vệ trước khi thao tác, dùng guard/query |
| Đọc object đơn lẻ bằng `@PostFilter` | Sai cơ chế với non-collection | `@PreAuthorize` hoặc `@PostAuthorize` tùy rủi ro |
| Kết quả đúng trong test không có proxy | Test gọi class mới thay vì bean | Test tích hợp với Spring context để kiểm tra advice |
| `@PreFilter` gọi DB từng phần tử rất chậm | Mỗi ID gây một lookup | Batch ownership query + guard tổng hợp |
| Cùng owner nhưng record khác tenant lộ | Username không duy nhất theo tenant | Bảo vệ theo subject + tenant/resource |
| `@PreAuthorize` cho phép nhưng update bị race | Quyền thay đổi sau lúc check | Transaction/conditional UPDATE/optimistic locking |

## 12. Một chương trình Java 17 nhỏ để nhìn rõ “lọc” và “từ chối”

Đây là ví dụ **Java thuần, không sử dụng Spring Security**. Nó chỉ minh họa sự khác biệt giữa **lọc từng phần tử** và **từ chối toàn bộ tập**; triển khai thật vẫn cần annotations/security proxy như project ở mục 5.

Tập tin **`OwnershipRuleDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class OwnershipRuleDemo {
    public static void main(String[] args) {
        Map<Long, String> ownerById =
            Map.of(1L, "alice", 2L, "bob", 3L, "alice");

        List<Long> requested = List.of(1L, 2L, 3L);

        List<Long> filtered = requested.stream()
            .filter(id -> "alice".equals(ownerById.get(id)))
            .toList();

        boolean allOwned = requested.stream()
            .allMatch(id -> "alice".equals(ownerById.get(id)));

        System.out.println("requested=" + requested);
        System.out.println("filtered=" + filtered);
        System.out.println("strictAllowed=" + allOwned);
    }
}
```

Chạy:

```bash
javac OwnershipRuleDemo.java
java OwnershipRuleDemo
```

**Stdout chính xác:**

```text
requested=[1, 2, 3]
filtered=[1, 3]
strictAllowed=false
```

Đây là bản mô phỏng `@PreFilter` so với chính sách nguyên tử `allOwned`. Không copy logic `Map.of` này vào production làm nguồn sự thật; owner map và quyền truy cập cần được xác minh tại database/authorization service.

## 13. Checklist trước khi hoàn tất bài kiểm thử method security

- [ ] Bật `@EnableMethodSecurity` và kiểm tra service method được gọi thông qua Spring-managed proxy.
- [ ] Phân biệt rõ **lọc phần tử** (`@PreFilter`, `@PostFilter`) với **từ chối thao tác** (`@PreAuthorize`).
- [ ] Biểu thức SpEL dùng `filterObject` đúng kiểu phần tử, `authentication` là principal được xác thực, `filterTarget` đúng tham số.
- [ ] Không tin `owner`/`tenantId` do client gửi; kiểm tra ID ở repository và dùng tenant claim/member hợp lệ.
- [ ] Với `@PreFilter`, collection có tính mutable phù hợp, không truyền thẳng immutable list khiến filter lỗi.
- [ ] Với `@PostFilter`, method trả collection tương thích và không có side effects hoặc log dữ liệu chưa được authorize.
- [ ] Với danh sách lớn/pagination, dùng **repository query lọc theo owner/tenant** thay vì load-all rồi hậu lọc.
- [ ] Với cập nhật/dữ liệu nhạy cảm, dùng guard trước side effect, transaction và update có điều kiện.
- [ ] Test Alice và Bob, mixed IDs, fake owner, forbidden ID, empty/missing ID, chưa đăng nhập và cross-tenant.
- [ ] Test cả service proxy với `@WithMockUser` và HTTP MockMvc; không nhầm test mock authentication với xác minh token thật.
- [ ] Kiểm tra 401/403/200 và việc dữ liệu người khác **không xuất hiện trong JSON**, logs, counters, side effects hoặc exceptions.
- [ ] Nếu dùng `@PostAuthorize`, phân tích side effects đã xảy ra trước check; không dùng để bảo vệ thao tác ghi không thể rollback.

**Kết luận:** `@PreFilter` chỉ cho method nhận các phần tử được phép; `@PostFilter` chỉ cho caller nhìn thấy phần tử được phép trong kết quả trả về. Cả hai **không tự bảo đảm rằng một batch có foreign ID sẽ bị từ chối**, và cũng không tự ngăn service truy vấn dữ liệu người khác trước khi lọc. Bài kiểm thử đúng phải chứng minh cả **không lộ dữ liệu của chủ sở hữu khác** lẫn **không thực hiện hành động sai quyền**, với policy đối chiếu owner/tenant từ server, không phải từ dữ liệu client khai báo.
