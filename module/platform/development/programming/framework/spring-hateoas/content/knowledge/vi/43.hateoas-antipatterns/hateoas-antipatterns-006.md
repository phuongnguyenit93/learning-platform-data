# Assembler chứa nghiệp vụ

## Mục tiêu

RepresentationModelAssembler có nhiệm vụ chuyển một đối tượng hoặc projection thành representation model, sau đó gắn các links cần thiết. Khi assembler bắt đầu truy vấn repository, gọi dịch vụ từ xa, thay đổi entity hoặc tự quyết định quy tắc nghiệp vụ, nó đang gánh trách nhiệm của application service và domain layer.

Đây là anti-pattern vì logic nghiệp vụ bị trộn với cách biểu diễn HTTP. Một assembler có thể chạy trong nhiều controller hoặc được tái sử dụng cho nhiều client, nhưng các quyết định nghiệp vụ lại phụ thuộc transaction, người gọi, tenant và trạng thái dữ liệu. Kết quả thường là code khó kiểm thử, phát sinh N+1 queries và tạo representation không nhất quán.

Sau bài học, bạn có thể:

- Nhận diện dấu hiệu assembler đang chứa nghiệp vụ.
- Phân biệt mapping representation với quyết định nghiệp vụ.
- Đưa truy vấn và policy vào application/domain service.
- Truyền projection đã chuẩn bị vào assembler.
- Tạo conditional links từ kết quả policy mà không gọi lại nghiệp vụ.
- Kiểm thử riêng policy, assembler và HTTP representation.

## Trách nhiệm đúng của assembler

Trong Spring HATEOAS, RepresentationModelAssembler<T, D> nhận một đối tượng nguồn kiểu T và chuyển thành representation model kiểu D. Phương thức chính là toModel(T). Interface cũng hỗ trợ chuyển một tập nguồn thành CollectionModel thông qua toCollectionModel(...).

Một assembler thường làm các việc sau:

- Chọn những field cần công bố trong response.
- Chuyển kiểu dữ liệu domain/projection thành DTO hoặc representation model.
- Tạo self link và các resource links theo controller mapping.
- Thêm links theo những khả năng đã được application layer xác định.
- Tạo collection representation từ các item representation.

Assembler có thể quyết định cách trình bày một kết quả đã có. Ví dụ, nếu OrderView có canCancel=true, assembler thêm relation cancel. Nó không nên tự tải đơn hàng, kiểm tra quyền trong database, tính điều kiện chuyển trạng thái rồi mới quyết định giá trị canCancel.

Ranh giới thực tế:

| Trách nhiệm | Nơi phù hợp |
|---|---|
| Tải order và dữ liệu liên quan | Repository/query service |
| Kiểm tra tenant, owner và quyền nghiệp vụ | Authorization/domain policy |
| Kiểm tra trạng thái có thể hủy hay không | Domain model hoặc domain policy |
| Điều phối các truy vấn và policy cho một use case | Application service |
| Chọn field DTO, tạo self/action links | Representation assembler |
| Xác thực và phân quyền request thực tế | Spring Security và application/domain layer |

Không cần tách một method mapping đơn giản thành nhiều lớp. Vấn đề xuất hiện khi assembler trở thành nơi thực hiện use case hoặc chứa các quyết định có ý nghĩa nghiệp vụ.

## Dấu hiệu của assembler chứa nghiệp vụ

Một số dấu hiệu dễ nhận biết:

- Inject repository chỉ để tìm entity hoặc dữ liệu liên quan trong toModel(...).
- Inject REST client hoặc WebClient để gọi service khác cho từng item.
- Mở transaction, lưu entity hoặc gọi method làm thay đổi trạng thái.
- Tự quyết định đơn hàng có được hủy, hoàn tiền, duyệt hay không.
- Đọc security context rồi tự thực hiện truy vấn phân quyền phức tạp.
- Tính tổng tiền, phí, hạn mức hoặc chính sách giá trong lúc tạo representation.
- Tạo một query riêng cho mỗi item khi dựng collection.
- Có nhiều nhánh nghiệp vụ lồng nhau khiến toModel(...) khó đọc và khó kiểm thử.

Ví dụ assembler đang làm quá nhiều việc:

~~~java
@Component
class OrderAssembler {

    private final OrderRepository orders;
    private final CustomerClient customerClient;
    private final OrderAuthorization authorization;

    EntityModel<OrderResponse> toModel(
            UUID orderId,
            CurrentUser currentUser) {

        Order order = orders.findById(orderId).orElseThrow();
        Customer customer = customerClient.getCustomer(order.customerId());

        boolean canCancel = authorization.canCancel(currentUser, order);
        if (canCancel && order.status() == OrderStatus.PENDING) {
            order.markCancellationRequested();
            orders.save(order);
        }

        OrderResponse response = new OrderResponse(
                order.id(),
                order.status().name(),
                customer.displayName());

        EntityModel<OrderResponse> model = EntityModel.of(response);
        model.add(linkTo(methodOn(OrderController.class)
                .findById(order.id()))
                .withSelfRel());
        return model;
    }
}
~~~

Đoạn code này có nhiều vấn đề:

1. toModel nhận ID thay vì một đối tượng đã được query service chuẩn bị.
2. Mỗi lần lắp ráp có thể phát sinh truy vấn và network call.
3. Kết quả phụ thuộc latency và lỗi của CustomerClient.
4. Chỉ đọc representation lại có thể thay đổi trạng thái đơn hàng.
5. Quy tắc hủy đơn bị đặt trong lớp chuyên chuyển đổi dữ liệu.
6. Khó tạo collection lớn mà không phát sinh N+1 queries.

Đặc biệt, điều kiện canCancel không nên dẫn tới side effect trong assembler. Việc công bố một action link chỉ mô tả khả năng; nó không phải lệnh thực hiện hành động.

## Tách application service và policy

Application service điều phối dữ liệu cần cho use case đọc representation. Domain policy hoặc domain model quyết định các điều kiện nghiệp vụ. Assembler nhận kết quả đã chuẩn bị và chỉ chuyển nó thành representation.

Ví dụ một policy thuần:

~~~java
class OrderPolicy {

    boolean canCancel(Order order, CurrentUser user) {
        return user.hasAuthority("orders:cancel")
                && order.tenantId().equals(user.tenantId())
                && order.status() == OrderStatus.PENDING
                && !order.hasShipment();
    }
}
~~~

Policy chỉ đọc trạng thái và trả về quyết định. Nó không tạo link, không phụ thuộc Spring MVC và không biết response sẽ dùng HAL hay media type khác.

Query service tải dữ liệu và tạo projection dành cho representation:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

record OrderView(
        UUID id,
        String status,
        BigDecimal total,
        String customerName,
        boolean canCancel) {
}

record OrderResponse(
        UUID id,
        String status,
        BigDecimal total,
        String customerName) {
}
~~~

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderQueryService {

    private final OrderRepository orders;
    private final OrderPolicy policy;

    OrderQueryService(OrderRepository orders, OrderPolicy policy) {
        this.orders = orders;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    OrderView findView(UUID orderId, CurrentUser currentUser) {
        Order order = orders.findDetailedByIdAndTenantId(
                        orderId,
                        currentUser.tenantId())
                .orElseThrow(OrderNotFoundException::new);

        return new OrderView(
                order.id(),
                order.status().name(),
                order.total(),
                order.customerName(),
                policy.canCancel(order, currentUser));
    }
}
~~~

Ví dụ giả định repository có truy vấn lấy đủ dữ liệu cần dùng và giới hạn theo tenant ngay ở database. Nếu customer nằm ở service khác, application service có thể điều phối việc lấy dữ liệu theo batch hoặc dùng một read model phù hợp. Không nên gọi service ngoài một lần cho từng item trong assembler.

Projection OrderView chứa kết quả policy canCancel. Giá trị này được tính trong use case đọc, không phải được assembler tự suy ra từ tên role hoặc trạng thái đơn hàng.

## Assembler chỉ ánh xạ và tạo links

Assembler nhận OrderView, chuyển các field thành response DTO và tạo links từ controller mapping:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<OrderView, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(OrderView view) {
        OrderResponse response = new OrderResponse(
                view.id(),
                view.status(),
                view.total(),
                view.customerName());

        EntityModel<OrderResponse> model = EntityModel.of(
                response,
                linkTo(methodOn(OrderController.class)
                        .findById(view.id()))
                        .withSelfRel());

        model.addIf(view.canCancel(), () ->
                linkTo(methodOn(OrderController.class)
                        .cancel(view.id()))
                        .withRel("cancel"));

        return model;
    }
}
~~~

Assembler không cần biết cách canCancel được tính. Nó chỉ dùng kết quả để quyết định có công bố relation hay không. addIf(...) trì hoãn việc tạo link cho tới khi điều kiện đúng, nhưng quyết định nghiệp vụ đã được chuẩn bị trước khi gọi assembler.

Controller điều phối hai lớp:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderQueryService queries;
    private final OrderCommandService commands;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderQueryService queries,
            OrderCommandService commands,
            OrderModelAssembler assembler) {
        this.queries = queries;
        this.commands = commands;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> findById(
            @PathVariable UUID id,
            @AuthenticationPrincipal CurrentUser currentUser) {
        return assembler.toModel(queries.findView(id, currentUser));
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            @AuthenticationPrincipal CurrentUser currentUser) {
        commands.cancel(id, currentUser);
        return ResponseEntity.noContent().build();
    }
}
~~~

OrderCommandService.cancel(...) phải kiểm tra lại quyền và trạng thái trong use case ghi. canCancel trong projection chỉ giúp representation công bố đúng khả năng tại thời điểm đọc; nó không thay thế authorization trên command endpoint.

Ví dụ command service dùng lại policy nhưng vẫn tải trạng thái mới nhất trong transaction:

~~~java
import java.util.UUID;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCommandService {

    private final OrderRepository orders;
    private final OrderPolicy policy;

    OrderCommandService(OrderRepository orders, OrderPolicy policy) {
        this.orders = orders;
        this.policy = policy;
    }

    @Transactional
    void cancel(UUID orderId, CurrentUser currentUser) {
        Order order = orders.findDetailedByIdAndTenantId(
                        orderId,
                        currentUser.tenantId())
                .orElseThrow(OrderNotFoundException::new);

        if (!policy.canCancel(order, currentUser)) {
            throw new AccessDeniedException("Order cannot be cancelled");
        }

        order.cancel();
    }
}
~~~

Domain method order.cancel() vẫn phải bảo vệ invariant chuyển trạng thái. Nếu nhiều request có thể cập nhật cùng đơn hàng đồng thời, dùng optimistic locking hoặc cơ chế concurrency phù hợp để tránh hai lệnh cùng dựa trên một trạng thái cũ.

## Không đưa side effect vào quá trình tạo representation

Assembler có thể được gọi nhiều lần cho cùng một entity: trong endpoint detail, collection, embedded resource, test hoặc một tác vụ xuất dữ liệu. Vì vậy, toModel(...) nên có tính chất chuyển đổi ổn định: cùng input và cùng request context thì tạo ra representation tương ứng, không làm thay đổi trạng thái nghiệp vụ.

Tránh những hành vi sau trong assembler:

~~~java
order.cancel();
repository.save(order);
paymentClient.refund(order.id());
eventPublisher.publishEvent(new OrderViewedEvent(order.id()));
~~~

Nếu việc đọc resource cần ghi audit log hoặc cập nhật lastViewedAt, hãy thể hiện đó là hành vi của use case trong application service. Đừng giấu side effect trong assembler, vì caller có thể không biết việc tạo JSON đã làm thay đổi dữ liệu.

Một số thao tác tạo representation có thể cần format ngày, tiền tệ hoặc trạng thái hiển thị. Những phép chuyển đổi thuần, không làm thay đổi domain và không gọi hạ tầng, vẫn có thể đặt trong mapper hoặc assembler nếu đơn giản. Khi logic format lớn hoặc dùng chung, tách thành mapper/presentation component.

## Tránh N+1 queries khi tạo collection

Assembler chứa repository thường tạo ra N+1 query:

1. Query lấy danh sách 100 đơn hàng.
2. toModel của mỗi đơn hàng query thêm customer.
3. Mỗi lần có thể query shipment, permission hoặc invoice.

Thay vì vậy, query service nên lấy dữ liệu cần thiết theo batch, dùng projection, fetch join hoặc query phù hợp. Sau đó assembler chỉ chuyển từng view thành model.

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

List<OrderView> views = orderQueryService.findViews(
        filter,
        currentUser);

CollectionModel<EntityModel<OrderResponse>> collection =
        assembler.toCollectionModel(views);
~~~

Nếu cần collection self link hoặc pagination links, controller hoặc một lớp resource assembler có thể bổ sung chúng sau khi collection được tạo. Không truy vấn lại dữ liệu chỉ để tạo link.

Không dùng fetch join tùy tiện với mọi quan hệ khi phân trang. Hãy kiểm tra query plan và số lượng bản ghi thực tế; projection hoặc batch loading thường phù hợp hơn cho read model.

## Khi cần conditional links theo quyền

Conditional links là một phần hợp lệ của representation. Điều cần tránh là để assembler tự xây dựng toàn bộ security policy.

Có hai cách phổ biến:

1. Application query service tính canCancel, canApprove hoặc tập action khả dụng và đưa vào view.
2. Một policy service chuyên biệt được gọi ở application layer, sau đó kết quả được chuyển vào assembler.

Với collection lớn, không gọi một remote authorization service cho từng item. Hãy dùng batch policy evaluation, scope truy vấn theo tenant hoặc lấy quyền một lần cho request nếu semantics cho phép.

Không nên để assembler tự đọc SecurityContextHolder rồi query role/tenant cho từng item. Cách đó làm phụ thuộc ngầm vào request context, khiến unit test khó hơn và khó tái sử dụng assembler ngoài HTTP request.

Ngay cả khi action link không được công bố, command service vẫn phải kiểm tra lại authorization và domain invariant. Người dùng có thể gọi endpoint trực tiếp hoặc dùng một link đã lưu từ response cũ.

## Kiểm thử theo đúng ranh giới

Tách test giúp phát hiện lớp nào đang nhận quá nhiều trách nhiệm:

| Lớp | Nội dung kiểm thử |
|---|---|
| Domain policy | Quy tắc quyền, tenant, owner và trạng thái. |
| Query/application service | Truy vấn đúng phạm vi, kết hợp dữ liệu và trả projection chính xác. |
| Assembler | Mapping field và thêm/bỏ relation dựa trên projection. |
| Controller/MockMvc | HTTP status, media type, href và serialization HAL. |
| Command service | Request trực tiếp vẫn bị từ chối khi thiếu quyền hoặc trạng thái không hợp lệ. |

Ví dụ unit test policy:

~~~java
@Test
void cannotCancelOrderFromAnotherTenant() {
    Order order = orderForTenant(tenantA, OrderStatus.PENDING);
    CurrentUser user = userWithAuthority(tenantB, "orders:cancel");

    assertThat(policy.canCancel(order, user)).isFalse();
}
~~~

Ví dụ test query service xác minh projection chứa kết quả policy:

~~~java
@Test
void returnsCancelAvailabilityInOrderView() {
    given(orders.findDetailedByIdAndTenantId(orderId, tenantId))
            .willReturn(Optional.of(pendingOrder));
    given(policy.canCancel(pendingOrder, currentUser)).willReturn(true);

    OrderView view = queries.findView(orderId, currentUser);

    assertThat(view.canCancel()).isTrue();
}
~~~

Ví dụ MockMvc test xác minh representation:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.hateoas.MediaTypes;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Test fixture cung cấp CurrentUser làm principal và cấu hình query service
// trả về OrderView có canCancel=true.
mockMvc.perform(get("/api/orders/{id}", orderId)
                .with(authentication(
                        new UsernamePasswordAuthenticationToken(
                                currentUser,
                                null,
                                List.of(new SimpleGrantedAuthority("orders:read")))))
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.cancel.href").exists());
~~~

Với trường hợp canCancel=false, kiểm tra $._links.cancel không tồn tại. Cần có thêm test POST trực tiếp tới cancel endpoint để xác minh authorization được thực thi ở server, kể cả khi relation bị ẩn.

Không cần mock repository trong assembler test vì assembler không nên phụ thuộc repository. Nếu muốn test URI được tạo đúng từ mapping, dùng MockMvc để có request context thực tế.

## Những lỗi thường gặp

- **Assembler nhận ID rồi tự tải entity:** chuyển truy vấn sang query/application service và truyền projection hoặc entity đã tải vào assembler.
- **Assembler gọi REST client:** điều phối dữ liệu ngoài ở application layer, ưu tiên batch hoặc read model.
- **Assembler thay đổi entity:** side effect thuộc command/use case, không thuộc quá trình biểu diễn.
- **Assembler tự quyết định nghiệp vụ:** đưa policy vào domain/application layer và truyền kết quả vào view.
- **Assembler tự đọc SecurityContextHolder:** truyền user context rõ ràng vào use case; không tạo phụ thuộc request ngầm.
- **Assembler tạo N+1 queries:** tải dữ liệu theo batch hoặc projection trước khi gọi toCollectionModel(...).
- **Dùng link visibility làm authorization:** command endpoint vẫn phải kiểm tra quyền và trạng thái.
- **Mock quá nhiều trong assembler test:** giữ assembler đơn giản để test mapping; kiểm tra hạ tầng ở query service và HTTP boundary.
- **Nhồi mọi phép format vào application service:** các chuyển đổi trình bày thuần có thể thuộc mapper/assembler; chỉ tách khi logic đủ phức tạp hoặc dùng chung.

## Quy trình refactor assembler chứa nghiệp vụ

1. Liệt kê mọi dependency mà assembler đang inject.
2. Phân loại từng hành vi: query, policy, command, integration call hay mapping.
3. Chuyển truy vấn và điều phối sang application/query service.
4. Chuyển invariant và quyết định nghiệp vụ sang domain model hoặc policy.
5. Tạo projection/view chứa dữ liệu và các kết quả khả năng cần cho representation.
6. Giữ assembler tập trung vào field mapping và link construction.
7. Kiểm tra collection path để loại bỏ N+1 queries.
8. Tách unit test cho policy, application service và assembler; thêm MockMvc contract test.
9. Xác minh command endpoint vẫn kiểm tra authorization và trạng thái độc lập với links.

Assembler không phải nơi thực hiện use case. Nó là ranh giới chuyển dữ liệu đã được chuẩn bị thành representation mà client có thể hiểu và điều hướng. Khi application service điều phối dữ liệu, domain policy quyết định nghiệp vụ và assembler chỉ ánh xạ cùng tạo links, code dễ kiểm thử hơn, collection tránh được truy vấn lặp và representation không gây side effect bất ngờ.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Representation models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models
- Spring HATEOAS API, RepresentationModelAssembler: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html
- Spring HATEOAS API, RepresentationModel: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html
- Spring Framework Reference Documentation, Data Access: https://docs.spring.io/spring-framework/reference/data-access.html
- Spring Data JPA Reference Documentation, Projections: https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html
