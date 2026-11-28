# Phân quyền dữ liệu module

Trong ứng dụng Spring Boot được chia thành các application module, việc xác định module nào sở hữu dữ liệu và module nào được phép gọi API của module khác giúp kiến trúc dễ kiểm soát. Nhưng **ranh giới module không tự động trở thành ranh giới bảo mật**. Một module có thể được đóng gói đúng theo Spring Modulith mà vẫn trả dữ liệu của tenant khác nếu service hoặc repository không kiểm tra quyền truy cập.

Phân quyền dữ liệu module cần trả lời ba câu hỏi:

1. Ai đang thực hiện thao tác?
2. Người đó có quyền thực hiện loại thao tác này không?
3. Người đó có quyền truy cập đúng bản ghi, tenant hoặc phạm vi dữ liệu này không?

Spring Security cung cấp authentication và authorization ở request/method level. Spring Modulith giúp giới hạn API và dependency giữa các module. Repository/query layer bảo đảm dữ liệu được lọc theo tenant, owner hoặc chính sách truy cập. Ba lớp này cần phối hợp với nhau.

Bài thuộc chương **Bảo mật** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mô-đun hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Bài này tập trung vào phân quyền dữ liệu tại ranh giới module, bao gồm cả cách ghi nhận dấu vết truy cập mà không làm lộ thông tin nhạy cảm.

> Ví dụ dùng Spring Security theo mô hình Servlet và Spring Modulith 2.2. Hãy chọn API/version tương thích với Spring Boot BOM của dự án. Các tên authority, tenant và module trong ví dụ là giả định để minh họa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt module encapsulation với runtime authorization.
2. Xác định nơi kiểm tra quyền ở HTTP request, service method và bản ghi dữ liệu.
3. Bật method security bằng `@EnableMethodSecurity`.
4. Dùng `@PreAuthorize` để bảo vệ use case của module.
5. Giới hạn truy vấn theo tenant và owner ngay tại repository.
6. Phân biệt quyền đọc dữ liệu của chính mình với quyền đọc toàn bộ dữ liệu trong tenant.
7. Bảo vệ API module khi module khác gọi qua public interface.
8. Xử lý identity và tenant khi domain event được xử lý bất đồng bộ.
9. Kiểm thử cả trường hợp được phép, bị từ chối và truy cập chéo tenant.
10. Ghi nhận audit/observability mà không đưa token hoặc dữ liệu cá nhân vào metrics.

## 2. Ranh giới module không phải ranh giới bảo mật

Spring Modulith mô hình hóa application module như một đơn vị chức năng gồm API được cung cấp, implementation nội bộ và các API mà module phụ thuộc. Theo mặc định, package gốc của module là API; package nội bộ không được module khác tham chiếu trực tiếp nếu chưa được expose qua named interface.

Ví dụ cấu trúc:

~~~text
com.example.shop
├── orders
│   ├── OrderManagement.java          // API của module
│   ├── OrderQuery.java               // API đọc dữ liệu
│   └── internal
│       ├── OrderRepository.java
│       ├── OrderEntity.java
│       └── OrderQueryService.java
├── customers
│   ├── CustomerManagement.java
│   └── internal
└── inventory
    ├── InventoryManagement.java
    └── internal
~~~

Spring Modulith có thể kiểm tra các dependency giữa application modules và named interfaces. Việc kiểm tra này giúp module khác không gọi thẳng `orders.internal.OrderRepository` hoặc phụ thuộc vào entity nội bộ.

Tuy nhiên, điều đó **không xác minh người dùng hiện tại có quyền đọc một đơn hàng cụ thể hay không**. Một method public vẫn có thể trả nhầm dữ liệu nếu không có authorization phù hợp.

| Cơ chế | Bảo vệ điều gì? | Ví dụ |
| --- | --- | --- |
| Spring Modulith module boundary | Cấu trúc phụ thuộc và khả năng truy cập API giữa các module | Module inventory chỉ gọi `OrderManagement` |
| Spring Security request authorization | Ai được gọi endpoint | Chỉ người đã đăng nhập được gọi `/api/orders/**` |
| Spring Security method authorization | Ai được gọi use case/service method | Cần authority `orders:read` |
| Tenant/resource scoping | Người gọi được đọc đúng bản ghi nào | Chỉ đọc order thuộc tenant của mình |
| Database constraints/policy | Tính toàn vẹn dữ liệu ở tầng lưu trữ | Foreign key hoặc row-level security nếu hệ thống sử dụng |

Không thay một lớp bằng lớp khác. Module boundary không thay authorization; `@PreAuthorize` không tự thêm điều kiện tenant vào SQL; repository filter không thay authentication.

## 3. Ba lớp phân quyền dữ liệu

Một request đọc đơn hàng có thể đi qua các lớp sau:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Authentication"]
    B --> C["Request authorization"]
    C --> D["Public API của module Orders"]
    D --> E["Method authorization"]
    E --> F["Lấy actor và tenant đáng tin cậy"]
    F --> G["Repository query có tenant/owner scope"]
    G --> H{"Bản ghi có thuộc phạm vi được phép?"}
    H -->|"Có"| I["Trả DTO đã được phép"]
    H -->|"Không"| J["404 hoặc 403 theo policy"]
~~~

### 3.1. Authentication — xác định actor

Authentication trả lời “ai đang gọi?”. Spring Security lưu đối tượng `Authentication` trong `SecurityContext`; principal định danh người dùng, còn authorities biểu diễn các quyền được cấp.

Một principal có thể chứa:

- `userId`: định danh nội bộ của người dùng.
- `tenantId`: tenant mà người dùng đang hoạt động.
- Authorities như `orders:read`, `orders:write`, `orders:read:any`.
- Các thuộc tính định danh khác đã được xác thực từ identity provider.

Không lấy `userId` hoặc `tenantId` từ query parameter hay request body rồi coi đó là danh tính đã xác thực. Client có thể sửa các giá trị này.

### 3.2. Authorization — xác định hành động được phép

Authorization trả lời “actor có được thực hiện hành động này không?”. Ví dụ:

- `orders:read`: đọc đơn hàng trong phạm vi được phép.
- `orders:write`: cập nhật đơn hàng trong phạm vi được phép.
- `orders:read:any`: đọc mọi đơn hàng trong tenant.
- `orders:admin`: thao tác quản trị theo policy của ứng dụng.

Dùng authority theo capability giúp biểu đạt quyền cụ thể hơn việc chỉ có một role `USER` hoặc `ADMIN`.

### 3.3. Data scope — xác định bản ghi được phép truy cập

Ngay cả khi actor có `orders:read`, họ chưa chắc được đọc mọi order. Query cần giới hạn theo tenant và owner hoặc một quan hệ chia sẻ được xác định.

Ví dụ:

- Người dùng A thuộc tenant X chỉ đọc order do A sở hữu trong X.
- Quản lý có `orders:read:any` được đọc order của các thành viên trong X.
- Người dùng thuộc tenant Y không được đọc bất kỳ order nào của X.

Đây là kiểm soát ở cấp resource/row. Nếu bỏ qua lớp này, endpoint có thể bị IDOR (Insecure Direct Object Reference): người dùng thay ID trên URL và nhận dữ liệu của người khác.

## 4. Bảo vệ HTTP endpoint

Spring Security request authorization giúp chặn truy cập ở cửa vào HTTP. Ví dụ:

~~~java
package com.example.shop.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health", "/actuator/health/**")
                    .permitAll()
                .requestMatchers("/actuator/**")
                    .hasAuthority("observability:read")
                .requestMatchers("/api/admin/**")
                    .hasAuthority("shop:admin")
                .requestMatchers("/api/**")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .build();
    }
}
~~~

Đoạn code minh họa các quy tắc authorization; cơ chế authentication như OAuth2 Resource Server, form login hoặc HTTP Basic cần được cấu hình theo cách ứng dụng thực sự xác thực người dùng.

Một số điểm cần lưu ý:

- Chỉ expose endpoint Actuator cần thiết. `prometheus`, `metrics` và `modulith` có thể tiết lộ thông tin về cấu trúc, hoạt động và tải của ứng dụng.
- Health details nên được giới hạn theo quyền phù hợp; không để response công khai tiết lộ host, database hoặc dependency nội bộ.
- Đặt management endpoint trong management network nếu kiến trúc triển khai hỗ trợ.
- Không dùng `permitAll()` cho toàn bộ `/actuator/**`.
- Không tắt CSRF một cách máy móc. Chỉ điều chỉnh CSRF theo cơ chế authentication, loại client và cách credential được gửi.

Request authorization là lớp đầu tiên. Người gọi vẫn có thể truy cập cùng service từ một endpoint khác, scheduler, message listener hoặc module khác. Vì vậy, use case cần được bảo vệ ở service layer.

## 5. Bật method security cho service của module

Spring Security không tự bật method-level authorization chỉ vì thêm `spring-boot-starter-security`. Cần khai báo `@EnableMethodSecurity` trong configuration:

~~~java
package com.example.shop.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Sau đó, bảo vệ public use case của module:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('orders:read')")
    @Transactional(readOnly = true)
    public OrderView findVisibleOrder(UUID orderId) {
        // Lấy actor từ adapter bảo mật và query theo tenant/owner.
        return null;
    }
}
~~~

`@PreAuthorize` kiểm tra quyền trước khi method chạy. Nếu không được phép, Spring Security ném `AccessDeniedException`. Trong HTTP request, exception translation có thể chuyển thành response 403. Khi method được gọi ngoài HTTP request, caller cần xử lý exception theo ngữ cảnh của nó.

### 5.1. Bảo vệ public API, không chỉ controller

Ví dụ controller có thể gọi public interface của module:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderQuery orderQuery;

    OrderController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping("/{id}")
    OrderView get(@PathVariable UUID id) {
        return orderQuery.findVisibleOrder(id);
    }
}
~~~

Module `orders` nên đặt authorization tại use case/service thực thi truy vấn. Như vậy, endpoint HTTP và các caller khác đều phải đi qua cùng policy.

### 5.2. Method security dựa trên Spring AOP proxy

Method security được thực thi thông qua interceptor/proxy của Spring. Vì vậy:

- Method cần được gọi thông qua Spring-managed bean.
- Lời gọi nội bộ kiểu `this.securedMethod()` không đi qua proxy như một lời gọi từ bean khác, nên không kích hoạt interceptor method security theo cách mong đợi.
- Không đặt policy duy nhất trên private method rồi kỳ vọng mọi caller đều bị kiểm tra.
- Test phải gọi method qua bean được Spring inject, không tự `new` service rồi gọi trực tiếp.

Có thể tách method public có security annotation và method private thực hiện logic nội bộ.

## 6. Phân quyền theo tenant và owner

Đây là lớp quan trọng nhất khi một bảng chứa dữ liệu của nhiều khách hàng hoặc tổ chức.

### 6.1. Principal và actor

Giả sử ứng dụng có principal tùy chỉnh:

~~~java
package com.example.shop.security;

import java.util.UUID;

public record ShopPrincipal(
        UUID userId,
        UUID tenantId
) {
}
~~~

Adapter đọc principal đã được authentication:

~~~java
package com.example.shop.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
class CurrentActor {

    Actor require() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            throw new IllegalStateException("No authenticated actor");
        }

        ShopPrincipal principal = (ShopPrincipal) authentication.getPrincipal();

        var authorities = authentication.getAuthorities().stream()
                .map(authority -> authority.getAuthority())
                .collect(java.util.stream.Collectors.toUnmodifiableSet());

        return new Actor(principal.userId(), principal.tenantId(), authorities);
    }
}
~~~

Đối tượng actor là dữ liệu nội bộ được tạo từ principal đã xác thực:

~~~java
package com.example.shop.security;

import java.util.Set;
import java.util.UUID;

public record Actor(
        UUID userId,
        UUID tenantId,
        Set<String> authorities
) {
    public boolean canReadAllOrders() {
        return authorities.contains("orders:read:any");
    }
}
~~~

Trong ứng dụng thực tế, có thể định nghĩa một interface `CurrentActor` ở application layer và implementation đọc `SecurityContext` ở adapter. Cách này giúp use case không phụ thuộc trực tiếp vào Spring Security API.

Ví dụ trên dành cho Servlet stack, nơi `SecurityContextHolder` thường dùng thread-local strategy. Với WebFlux, lấy security context từ Reactor context thay vì đọc `SecurityContextHolder` như ví dụ Servlet.

### 6.2. Repository query phải có scope

Entity đơn hàng có `tenantId` và `ownerId`. Repository định nghĩa các query có phạm vi rõ ràng:

~~~java
package com.example.shop.orders.internal;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, UUID> {

    Optional<OrderEntity> findByIdAndTenantId(
            UUID id,
            UUID tenantId
    );

    Optional<OrderEntity> findByIdAndTenantIdAndOwnerId(
            UUID id,
            UUID tenantId,
            UUID ownerId
    );
}
~~~

Service chọn query dựa trên quyền của actor:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderQueryService {

    private final OrderRepository repository;
    private final CurrentActor currentActor;
    private final OrderMapper mapper;

    OrderQueryService(
            OrderRepository repository,
            CurrentActor currentActor,
            OrderMapper mapper
    ) {
        this.repository = repository;
        this.currentActor = currentActor;
        this.mapper = mapper;
    }

    @PreAuthorize("hasAuthority('orders:read')")
    @Transactional(readOnly = true)
    public OrderView findVisibleOrder(UUID orderId) {
        Actor actor = currentActor.require();

        var order = actor.canReadAllOrders()
                ? repository.findByIdAndTenantId(orderId, actor.tenantId())
                : repository.findByIdAndTenantIdAndOwnerId(
                        orderId, actor.tenantId(), actor.userId());

        return order.map(mapper::toView)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Điểm quan trọng:

- Tenant ID được lấy từ actor đã xác thực, không lấy từ request body.
- Query luôn giới hạn theo tenant.
- Người có quyền đọc mọi order trong tenant vẫn không đọc được dữ liệu của tenant khác.
- Người không có quyền đọc toàn tenant phải khớp cả owner ID.
- DTO chỉ chứa field mà caller được phép xem.

Ví dụ dùng `OrderNotFoundException` cho cả trường hợp không tồn tại và không thuộc phạm vi truy cập giúp tránh tiết lộ ID của resource thuộc tenant khác. Nếu sản phẩm cần phân biệt 403 và 404, hãy áp dụng nhất quán và cân nhắc nguy cơ dò tìm resource.

### 6.3. Lọc danh sách ngay trong query

Không tải toàn bộ dữ liệu rồi lọc trong Java:

~~~java
Page<OrderEntity> findByTenantIdAndOwnerId(
        UUID tenantId,
        UUID ownerId,
        Pageable pageable
);
~~~

Với người quản lý được đọc toàn tenant:

~~~java
Page<OrderEntity> findByTenantId(
        UUID tenantId,
        Pageable pageable
);
~~~

Query và count query phải áp dụng cùng một scope. Nếu lọc sau khi phân trang, số lượng kết quả và trang dữ liệu có thể sai, đồng thời dữ liệu ngoài phạm vi vẫn đã được đọc vào application memory.

### 6.4. Bảo vệ cả thao tác ghi

Không chỉ truy vấn đọc mới cần tenant scope. Update/delete theo ID đơn thuần có thể sửa nhầm bản ghi của tenant khác.

Có thể dùng query có điều kiện:

~~~java
@Modifying
@Query("""
    update OrderEntity o
       set o.status = :status
     where o.id = :orderId
       and o.tenantId = :tenantId
       and o.ownerId = :ownerId
""")
int updateStatusIfOwned(
        UUID orderId,
        UUID tenantId,
        UUID ownerId,
        OrderStatus status
);
~~~

Nếu số dòng cập nhật bằng 0, resource không tồn tại hoặc không thuộc phạm vi cho phép. Với nghiệp vụ phức tạp, tải aggregate theo tenant scope rồi kiểm tra invariant trước khi thay đổi trong cùng transaction.

## 7. Kiểm tra quyền trên resource

Authority tổng quát như `orders:read` chưa đủ cho các policy phức tạp. Một resource có thể có trạng thái, quan hệ chia sẻ hoặc quyền theo dự án.

Có thể dùng authorization bean trong `@PreAuthorize`:

~~~java
@Service
class OrderCommandService {

    @PreAuthorize("@orderAuthorization.canUpdate(authentication, #orderId)")
    public void updateOrder(UUID orderId, UpdateOrderCommand command) {
        // Thực thi use case.
    }
}
~~~

Authorization component:

~~~java
@Component("orderAuthorization")
class OrderAuthorization {

    boolean canUpdate(Authentication authentication, UUID orderId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        // Kiểm tra authority, tenant và quan hệ với resource.
        // Dùng repository query có scope; không tin tenant từ request.
        return authentication.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("orders:write"));
    }
}
~~~

Đoạn code minh họa cuối chỉ kiểm tra capability; trong hệ thống thật, method phải xác minh cả tenant, owner hoặc policy chia sẻ của `orderId`. Không để method tên `canUpdate` chỉ kiểm tra role rồi bỏ qua quyền trên resource.

### 7.1. Vì sao không chỉ dùng PostAuthorize?

`@PostAuthorize` có thể kiểm tra giá trị trả về sau khi method thực thi, ví dụ:

~~~java
@PostAuthorize("returnObject.ownerId == authentication.name")
public OrderView readOrder(UUID orderId) {
    // ...
}
~~~

Cách này hữu ích với một số kết quả đã được tính toán, nhưng không nên là lớp duy nhất để bảo vệ dữ liệu tenant:

- Method đã đọc resource trước khi policy được đánh giá.
- Có thể thực hiện side effect hoặc truy vấn nhạy cảm trước khi bị từ chối.
- Dễ tải dữ liệu không cần thiết.
- Khó kết hợp với pagination và bulk query.
- Có thể làm lộ thông tin qua timing hoặc log nếu xử lý không cẩn thận.

Ưu tiên lọc theo tenant/owner ngay trong repository query. Dùng `@PostAuthorize` như lớp bổ sung khi thực sự cần kiểm tra return object.

### 7.2. Hạn chế PostFilter cho dữ liệu lớn

`@PostFilter` lọc collection sau khi method trả kết quả. Nếu repository đã tải hàng nghìn bản ghi, ứng dụng vẫn phải đọc và xử lý toàn bộ dữ liệu trước khi bỏ các phần tử không được phép.

Với dữ liệu lớn, pagination hoặc tenant isolation, hãy đưa điều kiện vào query. `@PreFilter` có thể phù hợp cho một số collection đầu vào nhỏ, nhưng không thay thế validation và authorization ở use case.

## 8. Gọi API giữa các module

Giả sử module `shipping` cần đọc địa chỉ giao hàng của order. Cách đúng là gọi public API của `orders`:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderShippingDetails {

    ShippingAddress getShippingAddress(UUID orderId);
}
~~~

Implementation nằm trong module `orders`:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderShippingDetailsImpl implements OrderShippingDetails {

    private final OrderQueryService orderQueryService;

    OrderShippingDetailsImpl(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Override
    @PreAuthorize("hasAuthority('orders:shipping:read')")
    public ShippingAddress getShippingAddress(UUID orderId) {
        return orderQueryService.getShippingAddressForCurrentActor(orderId);
    }
}
~~~

Module `shipping` không truy cập trực tiếp `OrderRepository` hoặc `OrderEntity` nội bộ. Module `orders` chịu trách nhiệm kiểm tra quyền và trả đúng DTO.

Cần phân biệt hai loại caller:

- **User-initiated call:** giữ actor/tenant của người dùng và áp dụng policy của người dùng.
- **Service-initiated call:** dùng service identity/capability được cấp rõ ràng, có scope giới hạn cho nghiệp vụ cần thực hiện.

Không cấp `ROLE_ADMIN` cho mọi service chỉ để tránh lỗi authorization. Hãy cấp quyền cụ thể như `orders:shipping:read` và kiểm tra tenant/resource phù hợp.

### 8.1. Module API không nên trả entity nội bộ

Không trả JPA entity hoặc object chứa mọi field của module cho caller khác. Dùng DTO theo use case:

- `OrderSummary`: mã đơn, trạng thái, thời điểm tạo.
- `ShippingAddress`: tên người nhận và địa chỉ cần thiết cho vận chuyển.
- `InvoiceData`: các trường phục vụ lập hóa đơn.

Việc tách DTO giúp module owner kiểm soát dữ liệu được expose và giảm nguy cơ caller sử dụng field nội bộ ngoài dự định.

## 9. Domain event và identity trong xử lý bất đồng bộ

Một domain event có thể được phát trong request của người dùng rồi được listener xử lý trên thread khác hoặc worker khác. Trong môi trường Servlet, `SecurityContextHolder` thường gắn với thread hiện tại; khi chuyển sang thread mới, context không tự có mặt trừ khi được truyền qua cơ chế hỗ trợ.

Vì vậy, listener không nên giả định rằng người dùng ban đầu vẫn có thể lấy được từ `SecurityContextHolder`.

### 9.1. Event chứa thông tin audit cần thiết

Ví dụ:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        UUID tenantId,
        UUID actorId,
        Instant occurredAt,
        String correlationId
) {
}
~~~

Event chứa thông tin định danh cần thiết cho audit và xử lý nghiệp vụ. Không đưa password, bearer token, session cookie hoặc toàn bộ `SecurityContext` vào payload.

Consumer có thể dùng `tenantId` và `actorId` để ghi audit, truy xuất policy hoặc gọi một service theo identity rõ ràng. Consumer vẫn cần xác minh event đến từ publisher đáng tin cậy và tenant/resource liên quan thực sự khớp.

### 9.2. Quyết định semantics của authorization

Với event thể hiện một sự kiện nghiệp vụ đã được chấp nhận, ví dụ `OrderPlaced`, authorization của command thường được kiểm tra tại thời điểm người dùng yêu cầu đặt hàng. Listener xử lý fact đó theo quyền của service consumer và các invariant nghiệp vụ.

Nếu consumer thực hiện một hành động mới thay mặt actor, policy có thể yêu cầu kiểm tra lại quyền hiện tại của actor. Khi đó, consumer cần tái dựng actor từ định danh đáng tin cậy và gọi authorization policy một cách tường minh.

Không dựa vào việc thread listener tình cờ còn `SecurityContext` để quyết định quyền.

### 9.3. Khi nào cần truyền SecurityContext qua executor?

Với một tác vụ ngắn hạn được submit từ request và có chủ đích thực thi dưới cùng security identity, Spring Security cung cấp `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextExecutor`. Wrapper đặt context cho tác vụ rồi xóa context sau khi chạy.

Ví dụ:

~~~java
Executor securedExecutor =
        new DelegatingSecurityContextExecutor(delegateExecutor);

securedExecutor.execute(() -> {
    securedService.performUserScopedOperation();
});
~~~

Chỉ dùng cách này khi việc kế thừa identity là chủ đích, thời gian sống của task ngắn và policy rõ ràng. Với message queue hoặc event xử lý sau nhiều phút/giờ, hãy dùng actor/service identity được biểu diễn rõ trong message và xác minh lại theo nghiệp vụ; không chuyển nguyên security context hoặc credential đã cũ.

## 10. Tenant isolation ở các điểm dễ bỏ sót

Tenant scope phải được áp dụng nhất quán trong toàn bộ đường truy cập dữ liệu:

| Thành phần | Điều cần kiểm tra |
| --- | --- |
| Repository | Mọi query đọc/ghi có tenant hoặc ownership predicate phù hợp |
| Pagination | Count query và content query dùng cùng scope |
| Search | Filter tenant trước khi tính kết quả hoặc highlight |
| Export/report | Không cho phép export dữ liệu toàn hệ thống bằng cách bỏ filter |
| Cache | Cache key có tenant và các dimension quyền cần thiết |
| File/object storage | Kiểm tra quyền trước khi cấp URL tải file |
| Background job | Job mang tenant scope hoặc service identity được giới hạn |
| Event listener | Xác minh tenant/resource trước side effect |
| Batch import | Mỗi dòng được kiểm tra tenant và quyền ghi |
| Admin/support tooling | Có quyền riêng, audit đầy đủ và phạm vi được phê duyệt |

### 10.1. Cache key phải chứa security scope

Nếu cache dùng key chỉ là `orderId`, một request của tenant X có thể nhận kết quả đã cache bởi tenant Y nếu ID hoặc cache namespace không được cô lập đúng.

Ví dụ:

~~~java
String cacheKey =
        actor.tenantId() + ":" + orderId + ":" + actor.userId();
~~~

Không phải mọi cache đều cần user ID trong key; chọn các chiều ảnh hưởng tới kết quả được phép. Với dữ liệu chỉ phụ thuộc tenant, tenant ID có thể đủ. Với dữ liệu phụ thuộc owner/role, phải bao gồm scope tương ứng hoặc cache kết quả đã được phân quyền theo cách khác.

### 10.2. Database row-level security là lớp bổ sung

Một số database hỗ trợ row-level security hoặc policy theo session. Có thể dùng để bổ sung defense-in-depth, nhất là khi nhiều ứng dụng hoặc job truy cập cùng database.

Nếu dùng, cần bảo đảm transaction luôn thiết lập tenant context đúng, pool connection không rò session state giữa request và policy cũng áp dụng cho background job. RLS không thay authorization ở application layer và phải được kiểm thử với connection pooling/transaction thực tế.

## 11. Kiểm thử phân quyền dữ liệu module

Test bảo mật cần kiểm tra cả quyền chức năng và phạm vi dữ liệu. Một test chỉ xác nhận user có role `USER` truy cập được endpoint chưa đủ để chứng minh tenant isolation.

### 11.1. Test method authorization

Spring Security Test cung cấp `@WithMockUser` để tạo Authentication trong test:

~~~java
@Test
@WithMockUser(authorities = "orders:read")
void readerCanCallReadUseCase() {
    // Gọi Spring-managed OrderQueryService bean.
}

@Test
@WithMockUser(authorities = "profile:read")
void userWithoutOrderPermissionIsDenied() {
    // Kỳ vọng AccessDeniedException.
}
~~~

Dùng authorities thay vì chỉ dựa trên tên role nếu policy trong code dùng `hasAuthority`. Khi cần principal tùy chỉnh có `userId` và `tenantId`, tạo test annotation với `@WithSecurityContext` hoặc dùng `@WithUserDetails` để dựng đúng principal.

### 11.2. Test tenant isolation

Chuẩn bị dữ liệu:

| Order | Tenant | Owner |
| --- | --- | --- |
| O-100 | Tenant A | User A |
| O-101 | Tenant A | User B |
| O-200 | Tenant B | User C |

Các kỳ vọng:

- User A đọc được O-100.
- User A không đọc được O-101 nếu không có quyền đọc toàn tenant.
- User A không đọc được O-200 trong mọi trường hợp thông thường.
- Manager của Tenant A đọc được O-100 và O-101 nếu có `orders:read:any`.
- Manager Tenant A vẫn không đọc được O-200.

Kiểm thử ở service/repository integration layer, không chỉ mock repository rồi assert method được gọi.

### 11.3. Test HTTP status và data leakage

Gọi endpoint thật qua MockMvc hoặc WebTestClient tùy stack:

- Không authentication: 401 hoặc cơ chế challenge tương ứng.
- Có authentication nhưng thiếu authority: 403.
- Có authority nhưng resource ngoài tenant: 404 hoặc 403 theo policy đã chọn.
- Resource thuộc scope: 200 và DTO chỉ có field được phép.

Nếu dùng 404 cho resource ngoài phạm vi, test cả trường hợp ID không tồn tại để bảo đảm response không phân biệt hai trường hợp ngoài ý muốn.

### 11.4. Test module boundary

Ngoài authorization test, chạy module verification của Spring Modulith để phát hiện module khác tham chiếu package internal hoặc dependency không được khai báo.

Module verification xác minh cấu trúc phụ thuộc. Nó không thay thế các test tenant/owner ở trên.

### 11.5. Test event và background job

Kiểm thử listener khi không có `SecurityContext` để bảo đảm consumer không phụ thuộc ngầm vào request thread. Test thêm:

- Event có tenant ID hợp lệ.
- Event mang tenant ID không khớp aggregate.
- Actor ID được giữ cho audit.
- Consumer service identity chỉ có capability cần thiết.
- Retry không làm side effect lặp ngoài dự kiến.

## 12. Ghi nhận authorization và observability an toàn

Khi phân quyền bị từ chối, hệ thống cần đủ thông tin để audit và phát hiện hành vi bất thường. Tuy nhiên, log/metric/trace không được biến thành nơi rò rỉ dữ liệu.

### 12.1. Authorization denied event

Spring Security có `AuthorizationDeniedEvent`. Khi cấu hình `AuthorizationEventPublisher`, ứng dụng có thể lắng nghe event này để ghi audit:

~~~java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher publisher
) {
    return new SpringAuthorizationEventPublisher(publisher);
}
~~~

Listener audit chỉ nên ghi metadata cần thiết:

~~~java
@Component
class AuthorizationAuditListener {

    @EventListener
    void onDenied(AuthorizationDeniedEvent<?> event) {
        // Ghi actor, action, resource type, outcome và correlation ID
        // theo schema audit của ứng dụng; không ghi credential hoặc payload.
    }
}
~~~

Đừng ghi access token, password, session cookie, toàn bộ request body hoặc dữ liệu cá nhân không cần thiết. Nếu log actor/resource ID, áp dụng retention và quyền đọc audit log phù hợp.

### 12.2. Metric tags phải có cardinality thấp

Tags phù hợp cho metrics:

- `module=orders|inventory|customers`
- `operation=read|write|delete`
- `outcome=granted|denied`
- `reason=missing_authority|tenant_mismatch` nếu tập giá trị được kiểm soát

Tránh đưa vào metric labels:

- `userId`, `tenantId`, `orderId`.
- Email, số điện thoại hoặc địa chỉ.
- `traceId`, session ID.
- Token hoặc nội dung request.
- Exception message tùy ý.

Các giá trị định danh có thể tạo số lượng time series rất lớn và tiết lộ hoạt động của từng khách hàng. Nếu cần điều tra một lần truy cập, dùng audit log có kiểm soát hoặc trace exemplar/correlation ID theo policy riêng; không biến ID thành metric label.

### 12.3. Trace và log chỉ ghi metadata cần thiết

Với Spring Modulith, module entry observations giúp hiểu module nào được gọi và method nào tham gia tương tác. Có thể dùng các thuộc tính kỹ thuật như module identifier, operation type và outcome.

Không thêm toàn bộ principal, authorities, payload domain event hoặc tenant profile vào span attributes. Chỉ ghi những field đã được đánh giá là cần thiết và không nhạy cảm. Tracing là công cụ chẩn đoán, không phải kho lưu trữ audit đầy đủ.

## 13. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chỉ bảo vệ controller | Module API có thể được gọi từ nơi khác | Bảo vệ use case ở service layer |
| Nghĩ Spring Modulith tự phân quyền user | Module boundary chỉ kiểm soát cấu trúc phụ thuộc | Dùng Spring Security và resource policy |
| Chỉ kiểm tra `orders:read` | User có thể đọc order của tenant khác | Thêm tenant/owner scope vào query |
| Lấy tenant ID từ request body | Client có thể sửa tenant | Lấy từ principal đã xác thực |
| Query theo ID rồi mới kiểm tra tenant ở UI | Dữ liệu đã được tải và có thể rò qua response/log | Query có tenant predicate ngay từ đầu |
| Dùng `@PostFilter` cho hàng nghìn bản ghi | Tốn bộ nhớ và sai pagination | Lọc trong repository/database |
| Chỉ dùng `@PostAuthorize` | Method có thể đọc dữ liệu trước khi bị từ chối | Dùng pre-authorization và scoped query |
| Gọi method bảo vệ qua self-invocation | AOP proxy có thể không được kích hoạt | Gọi qua Spring bean proxy hoặc tách service |
| Cho service account quyền admin toàn hệ thống | Tăng blast radius khi bị lạm dụng | Least privilege theo capability và tenant |
| Dựa vào SecurityContext trong event listener | Context có thể mất khi đổi thread/process | Truyền actor metadata có kiểm soát và dùng service identity |
| Đưa tenant ID vào metric tag | Cardinality tăng và lộ hoạt động khách hàng | Dùng module/operation/outcome; audit ID ở log riêng |
| Cache chỉ theo resource ID | Có thể trả cache entry của tenant khác | Cache key phản ánh tenant và access scope |
| Không test tenant chéo | Test role pass nhưng dữ liệu vẫn bị lộ | Test hai tenant và nhiều owner |
| Expose toàn bộ Actuator | Lộ thông tin vận hành | Chỉ expose endpoint cần thiết và bảo vệ quyền |

## 14. Quy trình thiết kế policy cho một module

Khi thêm một use case mới vào module, thực hiện theo trình tự:

1. Xác định dữ liệu thuộc module nào và public API nào được expose.
2. Xác định actor type: người dùng, service account hay scheduled job.
3. Xác định capability cần có: read, write, approve, export hoặc admin.
4. Xác định resource scope: tenant, owner, project, team hoặc quan hệ chia sẻ.
5. Đặt request authorization ở HTTP boundary.
6. Đặt method authorization tại public use case của module.
7. Đưa tenant/owner predicate vào repository query và mutation.
8. Xác định DTO chỉ chứa dữ liệu cần cho caller.
9. Kiểm tra cache, search, export, file storage và event consumer cùng scope.
10. Viết positive, negative và cross-tenant tests.
11. Ghi audit event cho quyết định nhạy cảm.
12. Xác nhận logs/metrics/traces không chứa credential hoặc dữ liệu thừa.

## 15. Bài thực hành

### Bài 1 — Bật method security

Thêm `@EnableMethodSecurity` vào configuration. Tạo method `OrderQueryService.findVisibleOrder` với `@PreAuthorize("hasAuthority('orders:read')")`. Kiểm tra user thiếu authority bị từ chối.

### Bài 2 — Tenant-scoped query

Tạo hai tenant và ba order. Viết repository method theo `tenantId` và `ownerId`. Xác minh user tenant A không đọc được order của tenant B.

### Bài 3 — Quyền quản lý trong tenant

Thêm authority `orders:read:any`. Cho phép manager đọc tất cả order trong tenant của mình, nhưng vẫn chặn tenant khác. Kiểm tra cả danh sách và detail query.

### Bài 4 — Ngăn IDOR

Thay order ID trên URL bằng ID của user khác. Xác minh response không chứa dữ liệu ngoài scope và không tiết lộ resource existence ngoài policy đã chọn.

### Bài 5 — Module API

Tạo public interface `OrderShippingDetails`. Đảm bảo module shipping không inject repository nội bộ của orders. Bảo vệ API bằng authority riêng và tenant scope.

### Bài 6 — Event listener không có request context

Publish `OrderPlaced` từ request, sau đó xử lý listener bằng executor. Xác minh listener vẫn có actor ID/tenant ID cần thiết cho audit mà không phụ thuộc `SecurityContextHolder` của request.

### Bài 7 — Authorization audit

Cấu hình publisher cho `AuthorizationDeniedEvent`. Ghi actor/action/outcome/correlation ID vào audit record. Xác minh token và request payload không xuất hiện trong log.

### Bài 8 — Cache isolation

Cache `OrderView` theo tenant và resource scope. Gửi hai request từ hai tenant cho cùng một key giả lập; xác minh không có cache hit chéo tenant.

## 16. Câu hỏi ôn tập

1. Spring Modulith module boundary khác runtime authorization ở điểm nào?
2. Vì sao `@EnableMethodSecurity` cần được khai báo tường minh?
3. `@PreAuthorize` bảo vệ use case ở lớp nào?
4. Vì sao `orders:read` chưa đủ để cho phép đọc mọi order?
5. Tại sao tenant ID phải lấy từ principal đã xác thực?
6. Repository query cần lọc theo những thuộc tính nào trong mô hình tenant/owner?
7. Vì sao `@PostFilter` không phù hợp cho dữ liệu lớn và pagination?
8. Self-invocation ảnh hưởng thế nào tới method security proxy?
9. Module khác nên truy cập dữ liệu qua public API nào?
10. Vì sao event listener không nên phụ thuộc vào request `SecurityContext`?
11. Khi nào có thể dùng `DelegatingSecurityContextExecutor`?
12. Cache key cần phản ánh security scope như thế nào?
13. `AuthorizationDeniedEvent` có thể dùng để ghi nhận điều gì?
14. Vì sao không đưa `tenantId` hoặc `userId` vào metric tags?
15. Cần kiểm thử những trường hợp nào để xác minh tenant isolation?

## 17. Ghi nhớ

**Spring Modulith giữ ranh giới cấu trúc; Spring Security quyết định actor được gọi use case nào; repository query quyết định actor được đọc hoặc sửa bản ghi nào.** Muốn phân quyền dữ liệu module an toàn, phải kết hợp cả ba lớp.

Dùng `@EnableMethodSecurity` và `@PreAuthorize` để bảo vệ service API. Lấy tenant/user identity từ principal đã xác thực, rồi đưa tenant và owner scope vào truy vấn đọc/ghi ngay tại database. Không dựa vào controller, `@PostFilter` hoặc UI để cô lập dữ liệu.

Khi module khác gọi qua public API, module sở hữu dữ liệu vẫn chịu trách nhiệm kiểm tra quyền. Với event bất đồng bộ, biểu diễn actor/tenant metadata một cách có chủ đích và dùng service identity giới hạn quyền cho consumer. Cuối cùng, kiểm thử cross-tenant, bảo vệ cache và chỉ ghi audit/telemetry với metadata cần thiết để tránh rò rỉ dữ liệu.

### Tài liệu tham khảo chính thức

- [Spring Modulith 2.2 — Fundamentals: Application Modules, Encapsulation và Named Interfaces](https://docs.spring.io/spring-modulith/reference/2.2/fundamentals.html).
- [Spring Security — Method Security: @EnableMethodSecurity, @PreAuthorize và @PostAuthorize](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Servlet Authentication Architecture: Authentication, Principal và Authorities](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html).
- [Spring Security — Spring MVC Integration: @AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html).
- [Spring Security — Concurrency Support: DelegatingSecurityContextRunnable và DelegatingSecurityContextExecutor](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html).
- [Spring Security — Authorization Events: AuthorizationDeniedEvent](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html).
- [Spring Security Test — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html).
- [Spring Boot — Actuator Endpoints và bảo vệ management endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
