# Kiểm soát quyền truy cập và chi phí tải entity trong bước bind

## 1. Một tham số controller có thể gây truy cập dữ liệu

Trong chương **Tham số web** của module **SPRING_DATA_COMMONS**, việc đưa một entity vào chữ ký controller có thể làm phát sinh truy vấn trước khi thân method chạy.

Ví dụ khi Spring Data Web và chuyển đổi domain class đã được đăng ký:

~~~java
@GetMapping("/orders/{orderId}")
public OrderView detail(
        @PathVariable("orderId") PurchaseOrder order) {

    return toView(order);
}
~~~

Dù controller không ghi lời gọi repository, Spring có thể chuyển giá trị trên URL sang kiểu ID rồi tra cứu entity tương ứng. Khả năng này tiện cho một số màn hình, nhưng cần được đánh giá đồng thời trên hai trục:

- **Quyền truy cập:** entity nào được phép đi vào bộ nhớ và được sử dụng bởi request hiện tại?
- **Chi phí tải:** bao nhiêu lượt gọi dữ liệu, bao nhiêu thuộc tính hoặc quan hệ được nạp trước khi xử lý nghiệp vụ?

Một ID có thể chuyển đổi được và một bản ghi tồn tại chưa đủ để kết luận người dùng được phép đọc bản ghi đó.

Bài viết tập trung vào Spring MVC và cơ chế DomainClassConverter. Không suy rằng mọi cơ chế bind, JSON deserialization hoặc mọi module Spring Data đều có cùng đường thực thi.

## 2. DomainClassConverter làm gì và không tự biết điều gì?

Spring Data Web hỗ trợ chuyển tham số request hoặc path variable thành domain object. Đường chuyển đổi thông thường sử dụng kiểu ID của repository và một lookup tương ứng với findById; tài liệu mô tả repository có khả năng CRUD là điều kiện để hỗ trợ cơ chế này. [DomainClassConverter trong Spring Data Web](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

Có thể hình dung:

~~~text
"9102" trong path variable
    → chuyển thành Long
    → repository invoker tra cứu ID 9102
    → PurchaseOrder hoặc kết quả không tìm thấy
    → hoàn tất việc resolve tham số controller
~~~

Trong mã nguồn Spring Data Commons 3.5.1, nhánh chuyển sang entity lấy metadata kiểu ID rồi gọi repository invoker để tìm theo ID. Bản thân nhánh đó không tự bổ sung tenant hoặc chủ sở hữu từ request. [Mã nguồn DomainClassConverter 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/repository/support/DomainClassConverter.java)

Điều này không có nghĩa mọi hệ thống đều tra cứu toàn cục: dự án có thể áp dụng repository tùy biến, bộ lọc tenant hoặc kiểm soát tại database. Tuy nhiên, phải có bằng chứng cho chính cấu hình ấy. Không mặc định một method như findByIdAndTenantId sẽ tự được chọn chỉ vì repository có khai báo nó.

### 2.1. Các khái niệm không thay thế nhau

| Điều đã biết | Điều vẫn phải kiểm tra |
| --- | --- |
| Request đã xác thực | Người dùng có quyền với đối tượng này không? |
| ID đúng định dạng | ID có nằm trong phạm vi được phép đọc không? |
| Entity tồn tại | Entity có thuộc tenant hoặc chủ sở hữu phù hợp không? |
| Có vai trò đọc đơn hàng | Vai trò cho phép đọc mọi đơn hay chỉ một tập con? |
| URL có customerId và orderId | Order có thực sự thuộc customer đó không? |
| Entity có metadata createdBy | Chính sách đọc có dựa trên người tạo hay quy tắc khác? |

Một URL dùng UUID khó đoán hơn ID tăng dần cũng không thay thế kiểm tra quyền. Người dùng có thể biết ID qua dữ liệu khác, đường dẫn được chia sẻ hoặc chính các API của ứng dụng.

## 3. Thứ tự thực thi quyết định thời điểm kiểm tra quyền

Trong luồng MVC thông thường:

~~~text
Request
  → Security filter chain: xác thực và kiểm tra quyền theo request
  → Spring MVC chọn handler
  → Resolve/bind các tham số
      → có thể chuyển ID thành entity và gọi repository
  → Gọi controller, qua method-security proxy nếu có
  → Gọi service và xử lý nghiệp vụ
  → Map kết quả, serialize JSON hoặc render view
~~~

Spring MVC resolve giá trị đối số trước khi gọi handler method. Vì vậy, kiểm tra trong thân controller hoặc interceptor bảo vệ lời gọi method không thể quay ngược thời gian để ngăn một lookup đã xảy ra khi tạo đối số. Đây là hệ quả của thứ tự thực thi, cần phân biệt với việc cho phép hay từ chối kết quả cuối cùng. [Thứ tự resolve và invoke trong Spring Framework 6.2.8](https://raw.githubusercontent.com/spring-projects/spring-framework/v6.2.8/spring-web/src/main/java/org/springframework/web/method/support/InvocableHandlerMethod.java)

### 3.1. Vì sao @PreAuthorize trên controller chưa giải quyết chi phí bind?

~~~java
@PreAuthorize("hasAuthority('orders:read')")
@GetMapping("/orders/{orderId}")
public OrderView detail(
        @PathVariable("orderId") PurchaseOrder order) {

    return toView(order);
}
~~~

Annotation có thể bảo vệ lời gọi controller nếu method security được bật và proxy áp dụng đúng. Tuy nhiên, đối số order có thể đã được tải khi MVC chuẩn bị lời gọi đó.

Có thể xảy ra tình huống:

1. Người dùng qua được quy tắc request-level là authenticated.
2. MVC tải order theo ID.
3. Method security từ chối vì thiếu authority orders:read.
4. Response không trả entity, nhưng chi phí lookup đã phát sinh.

Để từ chối một nhóm request trước binding, đặt quy tắc đủ sớm trong security filter chain. Quy tắc theo URL/authority vẫn cần kết hợp với kiểm tra phạm vi đối tượng tại tầng dữ liệu. [Request authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)

### 3.2. Hậu kiểm không xóa được dữ liệu đã tải

PostAuthorize kiểm tra sau khi method trả kết quả; PostFilter lọc kết quả sau xử lý. Chúng hữu ích cho những chính sách phù hợp, nhưng không nên được coi là cách tránh I/O hoặc tránh materialize dữ liệu ngoài phạm vi. Method security cũng cần được kích hoạt bằng cấu hình tương ứng, chẳng hạn EnableMethodSecurity. [Method security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)

## 4. Xác định hợp đồng truy cập trước khi chọn cách bind

Giả sử ứng dụng có nhiều tenant. Đối với endpoint GET /orders/{orderId}, chọn chính sách minh họa:

- Người gọi phải có authority orders:read.
- Authority này cho phép đọc đơn hàng trong tenant hiện tại của người gọi.
- Tenant hiện tại được xác nhận từ ngữ cảnh xác thực đáng tin cậy.
- Đơn đã xóa mềm không xuất hiện trong API đọc thông thường.
- ID không tồn tại và ID ngoài phạm vi đều trả cùng một phản hồi không tìm thấy.
- Response chỉ chứa những field dành cho màn hình chi tiết tóm tắt.

Đây là quyết định của ví dụ, không phải quy tắc mặc định của Spring Data.

Nếu nghiệp vụ chỉ cho phép đọc đơn do chính người dùng tạo, điều kiện tenant là chưa đủ: query còn phải thể hiện điều kiện chủ sở hữu hoặc tập quyền tương ứng. Nếu hỗ trợ quản trị viên đọc xuyên tenant, hãy thiết kế quyền và đường truy vấn riêng có kiểm soát.

### 4.1. Tenant trên request không tự trở thành nguồn tin cậy

Request sau không chứng minh người gọi thuộc tenant A:

~~~http
GET /orders/9102?tenantId=A
~~~

Tương tự, header do client tự đặt hoặc tenantId trong request body không đủ làm căn cứ. Nếu client được chọn tenant đang hoạt động, ứng dụng phải xác nhận quan hệ thành viên và quyền của lựa chọn đó trước khi dùng nó.

Trong ví dụ dưới đây, lớp xác thực đã kiểm tra danh tính và tenant; controller không nhận tenant làm đầu vào nghiệp vụ.

## 5. Mẫu thiết kế: bind ID thuần rồi truy vấn trong phạm vi quyền

Chọn một ID scalar ở biên HTTP:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderReadService service;

    public OrderController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping("/orders/{orderId}")
    public OrderView detail(@PathVariable("orderId") long orderId) {
        return service.get(orderId);
    }
}
~~~

Việc chuyển chuỗi sang long không cần tra cứu PurchaseOrder. Sau bước parse, service có thể kiểm tra quyền và quyết định đúng query cần dùng.

Không coi việc đổi entity thành ID là đã hoàn tất bảo mật. Lợi ích ở đây là đưa thao tác tải dữ liệu về một vị trí có thể quản lý rõ ràng.

### 5.1. Biểu diễn principal đã được xác minh

Ví dụ dùng Java 17 trở lên. Mỗi public type trong các đoạn code sau được hiểu là một type riêng của cùng package.

~~~java
package com.example.orders;

import java.util.Objects;
import java.util.UUID;

public record AppPrincipal(UUID userId, UUID tenantId) {

    public AppPrincipal {
        Objects.requireNonNull(userId);
        Objects.requireNonNull(tenantId);
    }
}
~~~

Ứng dụng phải tạo principal này trong quy trình xác thực đáng tin cậy. Không tạo nó bằng cách chép trực tiếp userId hoặc tenantId do request gửi vào.

Một thành phần lấy actor từ SecurityContext:

~~~java
package com.example.orders;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class CurrentActor {

    public AppPrincipal require() {
        Authentication auth = SecurityContextHolder.getContext()
                .getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof AppPrincipal principal)) {
            throw new AccessDeniedException(
                    "Không có ngữ cảnh người dùng phù hợp");
        }

        return principal;
    }
}
~~~

Ví dụ kiểm tra kiểu principal để tránh diễn giải một principal khác thành tenant đang hoạt động. Cách cung cấp principal thực tế phụ thuộc cơ chế xác thực của ứng dụng.

Service tự lấy actor từ thành phần này thay vì cung cấp một tham số tenant tùy ý cho controller truyền xuống. Nếu hệ thống có tác vụ nền hoặc service-to-service, cần định nghĩa ngữ cảnh actor phù hợp cho từng đường gọi.

### 5.2. Query chọn đúng phạm vi và đúng dữ liệu cần trả

Dùng Spring Data JPA để minh họa một store cụ thể:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderView(Long id, String reference, BigDecimal total) {
}
~~~

Giả sử entity JPA tên PurchaseOrder có các property id kiểu Long, tenantId kiểu UUID, reference kiểu String, total kiểu BigDecimal và deleted kiểu boolean:

~~~java
package com.example.orders;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface OrderReadRepository
        extends Repository<PurchaseOrder, Long> {

    @Query("""
            select new com.example.orders.OrderView(
                o.id, o.reference, o.total
            )
            from PurchaseOrder o
            where o.id = :id
              and o.tenantId = :tenantId
              and o.deleted = false
            """)
    Optional<OrderView> findVisibleSummary(
            @Param("id") Long id,
            @Param("tenantId") UUID tenantId);
}
~~~

Query thể hiện cả phạm vi tenant lẫn dữ liệu cần cho response. Nó không lấy toàn bộ entity rồi mới kiểm tra tenant tại controller.

Constructor expression này là JPQL của JPA. Với MongoDB, JDBC hoặc module khác, cần dùng cách truy vấn và projection tương ứng. Khả năng tối ưu của projection phải được xác nhận theo module và query thực tế. [Projection và DTO trong Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)

Repository của ví dụ chỉ công bố đường đọc cần thiết. Việc không mở toàn bộ CRUD API giúp ý định rõ hơn, nhưng không phải một hàng rào bảo mật độc lập: các đường truy cập dữ liệu khác vẫn cần cùng chính sách.

### 5.3. Service giữ quyền, phạm vi và transaction ở cùng đường đọc

~~~java
package com.example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderReadService {

    private final OrderReadRepository repository;
    private final CurrentActor currentActor;

    public OrderReadService(
            OrderReadRepository repository,
            CurrentActor currentActor) {
        this.repository = repository;
        this.currentActor = currentActor;
    }

    @PreAuthorize("hasAuthority('orders:read')")
    @Transactional(readOnly = true)
    public OrderView get(long orderId) {
        if (orderId < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Mã đơn hàng không hợp lệ");
        }

        AppPrincipal actor = currentActor.require();

        return repository.findVisibleSummary(orderId, actor.tenantId())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Không tìm thấy đơn hàng"));
    }
}
~~~

Mẫu này giả định service là Spring bean, lời gọi đi qua proxy phù hợp và method security đã được bật:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Hai annotation của cấu hình trên thuộc org.springframework.context.annotation.Configuration và org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity.

Không gọi method được bảo vệ bằng một đường self-invocation rồi mặc định proxy vẫn kiểm tra quyền. Hãy kiểm thử chính đường gọi từ controller sang bean service.

Transaction ở service tạo ranh giới cho thao tác đọc của ví dụ. readOnly không tự cấp quyền hay thêm tenant predicate. Với JPA, transaction của repository và query method có quy tắc riêng; không suy rộng cấu hình JPA sang mọi store. [Transactionality của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)

## 6. Chặn sớm theo request và vẫn giới hạn query

Trong cấu hình HttpSecurity hiện có, một quy tắc đọc có thể được khai báo:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(HttpMethod.GET, "/orders/**")
            .hasAuthority("orders:read")
        .anyRequest().authenticated());
~~~

HttpMethod thuộc org.springframework.http. Cần tích hợp quy tắc với các endpoint, cơ chế xác thực và security filter chain thực tế của ứng dụng.

Hai lớp kiểm soát có mục tiêu riêng:

| Lớp | Mục tiêu |
| --- | --- |
| Request authorization | Từ chối sớm người không được dùng nhóm endpoint |
| Method security ở service | Bảo vệ đường nghiệp vụ khi được gọi qua các entry point khác |
| Điều kiện query theo actor/tenant | Chỉ trả đối tượng thuộc phạm vi truy cập |
| DTO đầu ra | Chỉ biểu diễn dữ liệu mà API có chủ đích công bố |

Authority orders:read là quyền sử dụng chức năng trong ví dụ. Nó không tự cho query biết tenant nào đang hoạt động.

Một query có predicate tenant vẫn có thể làm database đọc index hoặc page dữ liệu trong quá trình thực thi. Mục tiêu của predicate là không trả dữ liệu ngoài phạm vi vào kết quả ứng dụng; không nên diễn giải nó thành lời hứa không có bất kỳ I/O vật lý nào liên quan đến dữ liệu khác.

## 7. Không tải toàn cục chỉ để quyết định 403 hay 404

Một cách xử lý thường gây thêm chi phí:

~~~text
findById(orderId)
    → thấy entity tồn tại
    → kiểm tra tenant
    → trả 403 nếu khác tenant
~~~

Một biến thể khác là query theo tenant trước, sau đó gọi existsById toàn cục để phân biệt “không tồn tại” với “ngoài quyền”.

Nếu chính sách của API đã chọn che sự tồn tại của tài nguyên ngoài phạm vi, cả hai cách đều tạo thêm công việc không cần thiết và có thể làm phản hồi khác nhau theo sự tồn tại toàn cục.

Với query có phạm vi của ví dụ:

| Trường hợp | Kết quả theo hợp đồng |
| --- | --- |
| ID thuộc tenant hiện tại, chưa xóa | Trả OrderView |
| ID không tồn tại | 404 |
| ID thuộc tenant khác | 404 |
| ID của đơn đã xóa mềm | 404 |
| Người đã xác thực thiếu authority | Từ chối trước query nghiệp vụ nếu rule/proxy đúng |
| Chưa xác thực | Entry point bảo mật xử lý theo cấu hình |
| ID sai cú pháp hoặc ngoài miền hợp lệ | Phản hồi đầu vào không hợp lệ theo hợp đồng API |

Không phải mọi sản phẩm đều chọn che sự tồn tại. Nếu nghiệp vụ yêu cầu phân biệt 403 và 404, phải thiết kế quyền kiểm tra sự tồn tại và chi phí tương ứng một cách chủ động.

Lỗi database, timeout và lỗi mapping không được biến thành 404. Chúng không có cùng ý nghĩa với một query hợp lệ trả kết quả rỗng.

## 8. Bind hai entity không xác nhận quan hệ cha–con

Ví dụ:

~~~java
@GetMapping("/customers/{customerId}/orders/{orderId}")
public OrderView detail(
        @PathVariable("customerId") Customer customer,
        @PathVariable("orderId") PurchaseOrder order) {

    return toView(order);
}
~~~

Ngay cả khi cả hai đối số được tìm thấy, chưa có bằng chứng rằng order thuộc customer, hoặc cả hai thuộc tenant được phép.

Một đường truy vấn có chủ đích cần thể hiện các điều kiện phù hợp:

~~~sql
-- Minh họa điều kiện logic; tên bảng/cột tùy schema.
WHERE order_id = :orderId
  AND customer_id = :customerId
  AND tenant_id = :trustedTenantId
  AND deleted = false
~~~

Mô hình truy vấn cần phản ánh quyền đối với chính tài nguyên con. Không chỉ kiểm tra quyền với customer rồi bỏ qua quan hệ với order.

## 9. Ngân sách truy vấn phải tính cả trước và sau controller

Một cách phân tích hữu ích:

~~~text
Q_request =
    Q_authentication
  + Q_binding
  + Q_service
  + Q_mapping
  + Q_rendering
~~~

Đây là mô hình phân rã để đo, không phải công thức dự đoán số SQL chính xác.

Những nguồn chi phí cần xem xét:

| Nguồn | Ví dụ |
| --- | --- |
| Bind entity | Tra cứu theo ID trước khi vào handler |
| Nhiều tham số entity | Nhiều đường chuyển đổi độc lập |
| Kiểm tra quyền | Một lookup chủ sở hữu hoặc membership không được tính trước |
| Eager association trong JPA | Entity kéo theo dữ liệu quan hệ |
| Getter/mapper truy cập quan hệ lazy | Truy vấn phát sinh khi dựng DTO |
| JSON hoặc template đọc object graph | I/O có thể xuất hiện ở bước trình bày |
| Tải lại trong service | Controller đã bind entity, service lại tìm cùng ID |

Không khẳng định một lời gọi findById luôn bằng đúng một câu SQL. Persistence context, cache, fetch plan và provider có thể làm chi phí thay đổi. Cũng không giả định cùng ID được bind nhiều lần sẽ luôn được tái sử dụng.

Đối với store không có cơ chế lazy association như JPA, cách tính tải quan hệ sẽ khác. Vẫn cần đo số operation, dung lượng dữ liệu và thời gian chờ của module thực tế.

### 9.1. Mục tiêu đo cho ví dụ đọc tóm tắt

Có thể đặt ngân sách riêng cho thao tác đọc đơn hàng:

- Bị từ chối bởi rule request-level: không chạy query đọc đơn hàng.
- Service từ chối vì thiếu quyền: không gọi OrderReadRepository.
- Đọc một summary hợp lệ: một đường query summary có phạm vi.
- Không tồn tại hoặc ngoài tenant: cùng một đường query summary, không lookup toàn cục bổ sung.
- Serialize OrderView: không cần tải thêm quan hệ của PurchaseOrder.

Đây là mục tiêu thiết kế cần kiểm chứng. Nó không bao gồm những truy vấn xác thực hoặc quan sát hệ thống có thể xảy ra bên ngoài đường đọc đơn hàng.

Projection hoặc DTO chỉ có lợi khi query thật lấy đúng dữ liệu cần. Một mapper tải full entity rồi chép ba field sang DTO vẫn đã trả chi phí tải entity.

## 10. Transaction bắt đầu sau bind không bao trùm bind

Nếu entity được tải lúc resolve tham số, một transaction chỉ mở ở service phía sau không tự bao trùm lần tải trước đó.

Với JPA, cần xem xét:

- Entity còn managed hay đã detached ở thời điểm sử dụng?
- Persistence context có tiếp tục tồn tại trong request hay không?
- Getter quan hệ có gây truy vấn muộn hoặc lỗi truy cập lazy không?
- Dữ liệu dùng để quyết định cập nhật có được đọc lại trong transaction đúng phạm vi không?

Không thêm Transactional lên controller rồi mặc định mọi bước argument conversion sẽ nằm trong transaction đó. Thời điểm mở transaction cần được kiểm chứng theo vị trí proxy và luồng gọi.

Đối với lệnh cập nhật, nên bind ID cùng command DTO, tải dữ liệu được phép trong transaction nghiệp vụ, kiểm tra trạng thái và áp dụng thay đổi tại đó. Nếu có cạnh tranh đồng thời, dùng cơ chế version hoặc locking phù hợp với store và bất biến nghiệp vụ; một entity đã bind trước đó không phải bằng chứng trạng thái còn hiện hành. [Locking trong Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)

## 11. Entity lookup và mass assignment là hai vấn đề riêng

Có hai dạng đầu vào dễ bị trộn lẫn:

1. Chuyển một ID thành entity đã tồn tại.
2. Gán nhiều field do request gửi vào một object.

Đổi tham số entity thành ID giúp kiểm soát lookup, nhưng không ngăn một command DTO thiết kế quá rộng cho phép client gửi tenantId, ownerId, role hoặc trạng thái nội bộ.

Đối với cập nhật, hãy khai báo DTO chỉ chứa field được phép sửa. Giá trị tenant, actor và metadata kiểm soát phải đến từ phía server. Khi dùng property binding, WebDataBinder có thể giới hạn field được bind; phạm vi của thiết lập này cần đúng với cơ chế nhận dữ liệu đang dùng. [Cấu hình WebDataBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)

Không suy rằng setAllowedFields trong một binder tự áp dụng cho mọi request body được Jackson deserialize. Cần kiểm tra đúng đường binding.

## 12. Auditing không phải hệ thống phân quyền đọc

CreatedBy, LastModifiedBy, CreatedDate và LastModifiedDate mô tả ai tạo/sửa cùng thời điểm thay đổi. Chúng không tự giới hạn findById hoặc kiểm tra người hiện tại có được đọc entity hay không. [Auditing của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/auditing.html)

Nếu chính sách dùng người tạo làm chủ sở hữu, ứng dụng phải thể hiện quy tắc đó trong đường kiểm tra quyền hoặc query. Không mặc định “cùng createdBy” là điều kiện đủ cho mọi nghiệp vụ.

Đối với các quyết định truy cập, log có thể ghi actor, thao tác, mã tài nguyên đã chuẩn hóa, kết quả cho phép/từ chối và correlation ID. Tránh log toàn bộ entity chỉ để chẩn đoán binding: thao tác đó vừa có thể đưa dữ liệu không cần thiết vào log, vừa có thể gọi getter tốn chi phí.

## 13. Kiểm thử cả quyền truy cập lẫn thời điểm I/O

Một response bị từ chối chưa chứng minh không có dữ liệu được tải. Kiểm thử cần quan sát cả response và đường gọi repository.

| Tình huống | Phản hồi cần xác nhận | Bằng chứng dữ liệu cần quan sát |
| --- | --- | --- |
| Tenant A đọc đơn A | Thành công, đúng DTO | Query nhận tenant A |
| Tenant A đọc đơn B | Không tìm thấy theo chính sách | Không dùng lookup toàn cục làm fallback |
| ID không tồn tại | Cùng hợp đồng phản hồi | Chỉ đường query có phạm vi |
| Thiếu authority | Bị từ chối | Không gọi repository đọc đơn |
| ID sai định dạng | Lỗi đầu vào theo cấu hình | Không lookup entity |
| URL cha–con không khớp | Không trả tài nguyên con | Query hoặc policy kiểm tra quan hệ |
| JSON hoàn tất | Chỉ field API dự định | Không query quan hệ phát sinh |
| Cập nhật cạnh tranh | Đúng chính sách đồng thời | Version/lock được áp dụng đúng |

### 13.1. Minh họa test đường gọi có phạm vi

Giả sử test đã khởi tạo MVC context có security filter chain, method security, controller, service thật và OrderReadRepository được thay bằng Mockito mock. Có thể kiểm tra một trường hợp ngoài phạm vi:

~~~java
@Test
void lookupUsesAuthenticatedTenant() throws Exception {
    UUID tenantA = UUID.fromString(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    UUID userA = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

    var auth = new TestingAuthenticationToken(
            new AppPrincipal(userA, tenantA),
            null,
            "orders:read");

    when(repository.findVisibleSummary(9102L, tenantA))
            .thenReturn(Optional.empty());

    mvc.perform(get("/orders/{orderId}", 9102L)
                    .with(authentication(auth)))
            .andExpect(status().isNotFound());

    verify(repository).findVisibleSummary(9102L, tenantA);
    verifyNoMoreInteractions(repository);
}
~~~

Đoạn test dùng JUnit 5, Mockito, MockMvc và authentication request post-processor từ Spring Security Test. Nó minh họa cấu trúc kiểm chứng, không phải báo cáo đã chạy trong một dự án cụ thể.

Mock chỉ chứng minh tham số và đường gọi trong test. Nó không chứng minh JPQL thật có tenant predicate hoặc database trả đúng kết quả. Cần test tích hợp với fixture đơn của hai tenant để kiểm tra điều đó.

Trong ví dụ này principal là AppPrincipal tùy biến. Một test chỉ tạo principal mặc định bằng tên người dùng sẽ không tự cung cấp tenant; phải thiết lập ngữ cảnh xác thực tương ứng với thiết kế ứng dụng.

### 13.2. Đo chi phí mà không bị fixture và cache che khuất

Khi đo query:

1. Tạo fixture trước cửa sổ đo.
2. Xác định đang đếm repository invocation, SQL statement hay operation của driver.
3. Kiểm soát persistence context và cache theo mục tiêu đo.
4. Đo trọn request tới khi serialize xong, không dừng ở lúc controller trả về.
5. Tách I/O xác thực khỏi I/O đọc tài nguyên nếu đặt ngân sách riêng.
6. Đối chiếu cả số query, dữ liệu trả về và độ trễ.

Không biến “một query summary” thành lời hứa “toàn request chỉ có một SQL” khi còn các thành phần khác. Với kiểm thử quyền truy cập, cần thêm case gọi service qua proxy để chắc chắn lớp bảo vệ nghiệp vụ thực sự có hiệu lực.

## 14. Khi nào cân nhắc custom argument resolver?

Một ứng dụng có thể muốn controller nhận một đối tượng đã được xác nhận quyền truy cập. Khi đó có thể thiết kế annotation và HandlerMethodArgumentResolver riêng với hợp đồng rõ ràng:

- Lấy actor từ ngữ cảnh đã xác thực.
- Parse và giới hạn đầu vào.
- Gọi một đường query có phạm vi.
- Trả kiểu kết quả hẹp, phù hợp mục đích sử dụng.
- Chuẩn hóa lỗi và có instrumentation để đo chi phí.
- Được kiểm thử tại đúng thời điểm trước handler invocation.

Đây là một lựa chọn kiến trúc khi có nhu cầu tái sử dụng rõ ràng. Nó vẫn phát sinh I/O trong bước resolve nên phải được nhìn thấy trong ngân sách truy vấn.

Không đưa một converter toàn cục gọi service bên ngoài rồi cho rằng mọi nơi dùng ConversionService đều có cùng ngữ cảnh HTTP, cùng actor hoặc cùng transaction. Với một endpoint đơn giản, bind ID rồi gọi service thường dễ quan sát và điều chỉnh hơn.

## 15. Điều kiện chấp nhận của một đường bind có kiểm soát

Một thiết kế đủ rõ cho phạm vi đã chọn cần trả lời được:

1. Bước nào thực hiện lookup đầu tiên?
2. Quyền nào đã được kiểm tra trước lookup đó?
3. Actor và tenant đến từ nguồn nào?
4. Query có đồng thời giới hạn ID, tenant, quan hệ và trạng thái cần thiết không?
5. Kết quả ngoài quyền có bị materialize rồi mới lọc không?
6. Có lookup toàn cục bổ sung chỉ để phân biệt trạng thái lỗi không?
7. Dữ liệu nào được tải và field nào được công bố?
8. Mapping hoặc serialization có gây I/O ngoài dự kiến không?
9. Ranh giới transaction và kiểm soát đồng thời nằm ở đâu?
10. Test nào chứng minh cả quyền truy cập lẫn chi phí thực tế?

Tiện ích bind entity của Spring Data cần đi cùng một hợp đồng truy cập và một ngân sách tải dữ liệu có thể kiểm chứng. Đưa ID thuần qua biên HTTP, xác định actor đáng tin cậy và truy vấn trong đúng phạm vi giúp các abstraction repository, projection và metadata phục vụ được mục tiêu đó mà vẫn tôn trọng khả năng của từng store.
