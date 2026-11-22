# Không đặt nghiệp vụ trong resolver

Trong Spring for GraphQL, resolver (data fetcher) là điểm nối giữa một field trong GraphQL schema và mã Java xử lý field đó. Resolver nên nhận argument, principal hoặc parent object, gọi tầng application rồi chuyển kết quả thành response phù hợp với schema. Các quy tắc nghiệp vụ như tính giá, kiểm tra tồn kho, quyết định trạng thái đơn hàng, chuyển tiền hay xác minh quyền sở hữu phải nằm trong application/domain layer.

Tổ chức như vậy giúp nghiệp vụ không phụ thuộc GraphQL. Cùng một use case có thể được gọi từ GraphQL resolver, REST controller, message consumer hoặc scheduled job mà không phải sao chép quy tắc. Resolver cũng dễ kiểm thử hơn vì nó chỉ chịu trách nhiệm binding và điều phối.

## 1. Resolver có vai trò gì?

Spring for GraphQL dùng các annotated controller để ánh xạ method Java thành DataFetcher cho field trong schema:

| Annotation | Field được ánh xạ |
|---|---|
| `@QueryMapping` | Field thuộc type `Query`. |
| `@MutationMapping` | Field thuộc type `Mutation`. |
| `@SubscriptionMapping` | Field thuộc type `Subscription`. |
| `@SchemaMapping` | Field của một object type cụ thể. |
| `@BatchMapping` | Field được phân giải theo nhóm parent objects. |

Ví dụ:

```java
@Controller
class BookController {

    @QueryMapping
    Book bookById(@Argument String id) {
        // Spring for GraphQL đăng ký method này làm DataFetcher.
        return ...;
    }
}
```

`@QueryMapping`, `@MutationMapping` và `@SubscriptionMapping` là các shortcut của `@SchemaMapping` cho ba root operation type. Chúng giúp khai báo nơi GraphQL field được phân giải; bản thân annotation không yêu cầu đặt nghiệp vụ trong controller.

## 2. Vì sao không nên đặt nghiệp vụ trong resolver?

Resolver nằm ở biên giao tiếp GraphQL. Nó biết về GraphQL schema, argument binding, parent object, selection set và GraphQL context. Nếu nhồi toàn bộ quy tắc nghiệp vụ vào resolver, ứng dụng dễ gặp các vấn đề:

- **Phụ thuộc transport:** logic chỉ chạy được khi đi qua GraphQL; REST hoặc message consumer phải gọi lại hoặc sao chép code.
- **Khó kiểm thử:** muốn kiểm tra một quy tắc tính giá có thể phải khởi tạo GraphQL execution, schema và controller context.
- **Khó kiểm soát transaction:** nhiều repository call rải trong resolver và field mapping có thể tạo các transaction nhỏ, không bao phủ đúng một nghiệp vụ.
- **Dễ vi phạm invariant:** cùng một quy tắc có thể được triển khai khác nhau ở nhiều resolver.
- **Khó thay đổi schema:** đổi tên field hoặc cấu trúc input có thể kéo theo việc sửa code nghiệp vụ.
- **Khó xử lý lỗi nhất quán:** resolver có thể trả lỗi theo cách riêng, khiến cùng một business failure được biểu diễn khác nhau ở từng API.
- **Dễ tạo N+1:** field resolver tự truy vấn dữ liệu cho từng parent object mà không có batch loading.

Resolver có thể thực hiện mapping đơn giản, chuyển đổi kiểu dữ liệu ở biên hoặc gọi use case. Nó không nên tự quyết định nghiệp vụ.

## 3. Phân chia trách nhiệm giữa các tầng

Một cách tổ chức phổ biến:

```text
GraphQL client
      |
      v
GraphQL schema (SDL)
      |
      v
Resolver / @Controller
  - bind @Argument
  - lấy Principal / context
  - gọi use case
  - map kết quả ra GraphQL DTO
      |
      v
Application service / use case
  - điều phối một nghiệp vụ
  - xác minh quyền và điều kiện sử dụng
  - mở transaction
  - gọi domain và repository
      |
      v
Domain model / domain service
  - invariant
  - quy tắc tính toán
  - chuyển trạng thái hợp lệ
      |
      v
Repository / infrastructure
  - lưu và đọc dữ liệu
  - tích hợp database hoặc hệ thống ngoài
```

| Tầng | Trách nhiệm | Ví dụ |
|---|---|---|
| GraphQL schema | Hợp đồng API, kiểu input/output, nullability | `PlaceOrderInput`, `Order`. |
| Resolver | Binding và điều phối | Lấy user từ `Principal`, gọi `PlaceOrderUseCase`. |
| Application | Điều phối use case và transaction | Đặt hàng, chuyển tiền, hoàn đơn. |
| Domain | Quy tắc và invariant | Số lượng phải dương, không cho đặt đơn đã đóng. |
| Infrastructure | Truy cập dữ liệu và tích hợp | JPA repository, R2DBC, HTTP client. |

Không phải dự án nào cũng cần đủ package hoặc class cho mọi tầng. Điều quan trọng là quy tắc nghiệp vụ có một nơi sở hữu rõ ràng và không bị phụ thuộc vào GraphQL.

## 4. Ví dụ: mutation đặt hàng

Giả sử API cho phép client đặt một đơn hàng. Schema:

```graphql
input OrderItemInput {
    productId: ID!
    quantity: Int!
}

input PlaceOrderInput {
    customerId: ID!
    items: [OrderItemInput!]!
}

type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}

type Order {
    id: ID!
    status: String!
    totalAmount: Float!
}
```

GraphQL schema chịu trách nhiệm kiểm tra cấu trúc và kiểu dữ liệu. Ví dụ `quantity` phải là `Int`, `input` không được null và danh sách `items` không được null. Nhưng SDL không thể quyết định sản phẩm còn hàng hay khách hàng có quyền đặt hàng.

## 5. Resolver mỏng: chỉ bind input và gọi use case

DTO nhận input ở biên GraphQL:

```java
import java.util.List;

public record OrderItemInput(String productId, int quantity) {}

public record PlaceOrderInput(
    String customerId,
    List<OrderItemInput> items
) {}
```

Command của application layer không cần biết GraphQL:

```java
import java.util.List;

public record PlaceOrderCommand(
    String actorId,
    String customerId,
    List<PlaceOrderLine> lines
) {}

public record PlaceOrderLine(String productId, int quantity) {}
```

Resolver chuyển input thành command và gọi use case:

```java
import java.security.Principal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderMutationController {

    private final PlaceOrderUseCase placeOrder;

    OrderMutationController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @MutationMapping
    OrderView placeOrder(
            @Argument PlaceOrderInput input,
            Principal principal) {

        PlaceOrderCommand command = new PlaceOrderCommand(
            principal.getName(),
            input.customerId(),
            input.items().stream()
                .map(item -> new PlaceOrderLine(
                    item.productId(), item.quantity()))
                .toList()
        );

        PlaceOrderResult result = placeOrder.execute(command);
        return OrderView.from(result);
    }
}
```

Resolver không tính tổng tiền, kiểm tra tồn kho, cập nhật trạng thái hay gọi repository. Nó chỉ chuyển GraphQL input thành application command, lấy danh tính đã xác thực và chuyển application result thành GraphQL view.

Model trả về ở biên GraphQL:

```java
import java.math.BigDecimal;

public record OrderView(
    String id,
    String status,
    BigDecimal totalAmount
) {
    static OrderView from(PlaceOrderResult result) {
        return new OrderView(
            result.orderId(),
            result.status().name(),
            result.totalAmount()
        );
    }
}
```

`OrderView` là response model của GraphQL. Nó có thể thay đổi theo API mà không buộc domain aggregate phải thay đổi theo.

Application result cũng là kiểu của application layer, không phụ thuộc GraphQL:

```java
public record PlaceOrderResult(
    String orderId,
    OrderStatus status,
    BigDecimal totalAmount
) {
    static PlaceOrderResult from(Order order) {
        return new PlaceOrderResult(order.id(), order.status(), order.total());
    }
}
```

## 6. Application service điều phối nghiệp vụ

Application service nhận command và điều phối các bước của một use case:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PlaceOrderUseCase {

    private final CustomerRepository customers;
    private final ProductRepository products;
    private final OrderRepository orders;
    private final PricingPolicy pricingPolicy;

    PlaceOrderUseCase(
            CustomerRepository customers,
            ProductRepository products,
            OrderRepository orders,
            PricingPolicy pricingPolicy) {
        this.customers = customers;
        this.products = products;
        this.orders = orders;
        this.pricingPolicy = pricingPolicy;
    }

    @Transactional
    public PlaceOrderResult execute(PlaceOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(() -> new CustomerNotFoundException(command.customerId()));

        if (!customer.canBeManagedBy(command.actorId())) {
            throw new OrderNotAllowedException();
        }

        Set<String> productIds = command.lines().stream()
            .map(PlaceOrderLine::productId)
            .collect(Collectors.toSet());

        Map<String, Product> productsById = products.findAllById(productIds)
            .stream()
            .collect(Collectors.toMap(Product::id, Function.identity()));

        List<OrderLine> lines = command.lines().stream()
            .map(line -> {
                if (line.quantity() <= 0) {
                    throw new InvalidOrderQuantityException(line.productId());
                }

                Product product = productsById.get(line.productId());
                if (product == null) {
                    throw new ProductNotFoundException(line.productId());
                }

                if (!product.isAvailableForSale()) {
                    throw new ProductUnavailableException(line.productId());
                }

                return OrderLine.create(product, line.quantity());
            })
            .toList();

        Money total = pricingPolicy.calculate(lines, customer);
        Order order = Order.place(customer, lines, total);
        orders.save(order);

        return PlaceOrderResult.from(order);
    }
}
```

Đây là ví dụ minh họa, các repository, exception và domain type cần được triển khai theo mô hình dữ liệu của ứng dụng. Điểm chính là toàn bộ bước tạo đơn được gom trong một use case, có một ranh giới transaction rõ ràng.

## 7. Đặt invariant trong domain model

Application service điều phối use case; domain object sở hữu các quy tắc bảo vệ trạng thái hợp lệ của chính nó.

Ví dụ:

```java
import java.util.List;
import java.util.UUID;

public class Order {

    private final String id;
    private OrderStatus status;
    private final List<OrderLine> lines;
    private final Money total;

    private Order(
            String id,
            OrderStatus status,
            List<OrderLine> lines,
            Money total) {
        this.id = id;
        this.status = status;
        this.lines = List.copyOf(lines);
        this.total = total;
    }

    public static Order place(
            Customer customer,
            List<OrderLine> lines,
            Money total) {

        if (lines.isEmpty()) {
            throw new EmptyOrderException();
        }

        if (!customer.canPlaceOrder()) {
            throw new CustomerCannotOrderException();
        }

        return new Order(
            UUID.randomUUID().toString(),
            OrderStatus.PLACED,
            lines,
            total
        );
    }

    public void cancel() {
        if (status != OrderStatus.PLACED) {
            throw new OrderCannotBeCancelledException(id);
        }
        status = OrderStatus.CANCELLED;
    }

    public String id() { return id; }
    public OrderStatus status() { return status; }
    public Money total() { return total; }
}
```

Domain model không cần import `@Controller`, `@MutationMapping`, `GraphQLContext` hay `GraphQLError`. Quy tắc như “đơn đã giao không thể hủy” phải đúng dù lệnh hủy đến từ GraphQL, REST, message consumer hay batch job.

## 8. Phân biệt validation đầu vào và business validation

Có nhiều lớp kiểm tra khác nhau:

| Loại kiểm tra | Vị trí phù hợp | Ví dụ |
|---|---|---|
| GraphQL type/coercion | SDL và GraphQL Java | `quantity: Int!`, `input: PlaceOrderInput!`. |
| Cấu trúc đầu vào | DTO và Bean Validation | Chuỗi mã sản phẩm không được để trống, danh sách có giới hạn phần tử. |
| Quy tắc nghiệp vụ | Application/domain | Sản phẩm còn bán, khách hàng đủ điều kiện, số dư đủ. |
| Quyền truy cập | Security/application policy | Người gọi được phép đặt hàng cho customer đó. |
| Ràng buộc dữ liệu | Database | Unique constraint, foreign key, optimistic locking. |

Có thể dùng `@Valid` trên argument của resolver để kiểm tra cấu trúc input:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;

@MutationMapping
OrderView placeOrder(@Argument @Valid PlaceOrderInput input, Principal principal) {
    // bind và gọi use case
}
```

Nhưng không được chỉ dựa vào validation ở resolver. Use case và domain phải bảo vệ invariant vì chúng có thể được gọi từ những entry point khác.

## 9. Đặt transaction ở ranh giới use case

GraphQL không định nghĩa transaction semantics. Server và ứng dụng quyết định đơn vị công việc nào cần atomicity và isolation.

Với một mutation đặt hàng, thường cần một transaction bao phủ các thao tác database liên quan:

1. Tải customer và product.
2. Kiểm tra điều kiện nghiệp vụ.
3. Tạo order và order lines.
4. Cập nhật tồn kho hoặc reservation trong cùng transaction nếu chúng cùng database/transaction manager.
5. Lưu kết quả.

Đặt `@Transactional` trên application service method giúp ranh giới transaction trùng với use case:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransferMoneyUseCase {

    private final AccountRepository accounts;

    TransferMoneyUseCase(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public TransferResult execute(TransferCommand command) {
        Account source = accounts.findById(command.sourceId())
            .orElseThrow(AccountNotFoundException::new);
        Account target = accounts.findById(command.targetId())
            .orElseThrow(AccountNotFoundException::new);

        source.withdraw(command.amount());
        target.deposit(command.amount());

        accounts.save(source);
        accounts.save(target);

        return new TransferResult(source.getId(), target.getId());
    }
}
```

Resolver chỉ gọi `transferMoney.execute(command)`. Cả hai thay đổi số dư tham gia cùng transaction và được commit hoặc rollback theo transaction policy.

Spring for GraphQL cũng hỗ trợ đặt `@Transactional` trực tiếp trên `@MutationMapping` method. Cách đó tạo transaction quanh lời gọi controller method và là một lựa chọn hợp lệ khi method chính là ranh giới use case. Nếu muốn nghiệp vụ có thể tái sử dụng độc lập với GraphQL, đặt transaction trên application service method thường rõ ràng hơn.

`@Transactional` hoạt động thông qua Spring proxy. Vì vậy, lời gọi phải đi qua bean proxy; một method trong cùng class tự gọi method `@Transactional` khác (self-invocation) thường không kích hoạt transaction advice. Theo mặc định, Spring rollback với unchecked exception (`RuntimeException`) và `Error`; nếu business exception là checked exception và cần rollback, khai báo `rollbackFor` phù hợp. Hãy kiểm tra transaction manager và propagation khi một use case gọi các service khác.

## 10. Không giữ transaction mở cho toàn bộ GraphQL request

GraphQL cho phép client chọn nhiều field độc lập. Các nested field có thể được phân giải ở những thời điểm khác nhau, gọi nhiều service hoặc batch loader.

Giữ một transaction database mở từ đầu đến cuối toàn bộ GraphQL request có thể:

- Giữ connection và lock lâu hơn cần thiết.
- Bao trùm các field mà client tùy ý chọn.
- Làm transaction boundary phụ thuộc selection set.
- Gặp khó khăn với asynchronous/reactive data fetchers.
- Tăng nguy cơ transaction dài khi field gọi remote service.

Spring for GraphQL mô tả transaction-per-controller-method là cách đơn giản với ranh giới rõ ràng. Với kiến trúc phân tầng, có thể đặt cùng transaction boundary trên application service method được resolver gọi. Transaction toàn request là kỹ thuật nâng cao và cần kiểm soát execution strategy, thread/context và cleanup; không nên áp dụng như mặc định.

## 11. Nhiều mutation trong cùng một GraphQL request

GraphQL cho phép một request chứa nhiều root mutation field. Các root mutation được thực thi tuần tự theo semantics của GraphQL, nhưng điều đó không tự động khiến tất cả chúng nằm trong cùng một database transaction.

Ví dụ:

```graphql
mutation {
    reserve: reserveInventory(input: { productId: "p-1", quantity: 2 }) {
        reservationId
    }
    create: createOrder(input: { customerId: "c-1" }) {
        id
    }
}
```

Nếu mỗi resolver gọi một use case có `@Transactional`, mỗi use case có transaction riêng. Nếu `reserveInventory` thành công nhưng `createOrder` thất bại, transaction đầu tiên không tự rollback theo transaction thứ hai.

Nếu hai bước phải thành công hoặc thất bại cùng nhau, nên thiết kế một mutation/use case bao trọn nghiệp vụ:

```graphql
type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}
```

`PlaceOrderUseCase` sẽ điều phối reservation và tạo order trong cùng một transaction khi các thao tác cùng tham gia một transaction manager. Đừng dựa vào việc client gửi nhiều mutation field để tạo một business transaction.

## 12. Đừng đặt transaction trên nested field resolver để nối nghiệp vụ

Ví dụ không nên dùng:

```java
@Controller
class OrderController {

    @MutationMapping
    Order createOrder(@Argument OrderInput input) {
        return orderRepository.save(...);
    }

    @SchemaMapping
    @Transactional
    Customer customer(Order order) {
        return customerRepository.findById(order.customerId()).orElseThrow();
    }
}
```

Transaction của `createOrder` kết thúc khi method trả về. Nested field `customer` chạy sau đó và nếu có `@Transactional`, nó mở transaction riêng. Hai transaction không tự trở thành một đơn vị atomic chỉ vì chúng thuộc cùng GraphQL response.

Hãy để mutation use case lưu các thay đổi cần atomicity. Nested field resolver nên chỉ tải dữ liệu liên quan thông qua query service hoặc DataLoader, theo nhu cầu của selection set.

## 13. Tách Query service và Command use case

Read path và write path có nhu cầu khác nhau:

- Query service đọc dữ liệu, hỗ trợ filter, pagination, projection và DataLoader.
- Command use case thay đổi trạng thái, kiểm tra invariant và quản lý transaction.

Ví dụ query resolver:

```java
import java.security.Principal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderQueryController {

    private final OrderQueryService orderQueries;

    OrderQueryController(OrderQueryService orderQueries) {
        this.orderQueries = orderQueries;
    }

    @QueryMapping
    OrderView orderById(@Argument String id, Principal principal) {
        return orderQueries.findVisibleOrder(id, principal.getName());
    }
}
```

Query service có thể dùng projection hoặc read model để tải đúng dữ liệu cần thiết:

```java
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderReadRepository repository;

    OrderQueryService(OrderReadRepository repository) {
        this.repository = repository;
    }

    public OrderView findVisibleOrder(String orderId, String actorId) {
        return repository.findViewVisibleTo(orderId, actorId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
```

Read operation thường không cần transaction ghi. Nếu nghiệp vụ cần consistent snapshot hoặc nhiều query đọc phải cùng một isolation boundary, hãy khai báo read-only/transaction phù hợp ở query service, không mặc định bao toàn bộ GraphQL request.

## 14. Nested resolver chỉ xử lý quan hệ của field

Một resolver cho `Order.customer` có thể gọi query service:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderFieldController {

    private final CustomerQueryService customers;

    OrderFieldController(CustomerQueryService customers) {
        this.customers = customers;
    }

    @SchemaMapping(typeName = "Order", field = "customer")
    CustomerView customer(Order order) {
        return customers.findById(order.customerId());
    }
}
```

Resolver này không quyết định có được hủy đơn, tính lại giá hay thay đổi trạng thái. Nó chỉ phân giải quan hệ `customer` để đáp ứng field được client chọn.

Nếu query trả về nhiều order, resolver trên có thể gây N+1. Khi đó, dùng `@BatchMapping` hoặc DataLoader để tải nhiều customer cùng lúc. Logic query và quyền truy cập vẫn ở service/repository; batch mapping chỉ là cách tối ưu việc lấy dữ liệu.

## 15. Dùng `@BatchMapping` mà không chuyển nghiệp vụ vào controller

Ví dụ batch mapping:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class OrderFieldController {

    private final CustomerQueryService customers;

    OrderFieldController(CustomerQueryService customers) {
        this.customers = customers;
    }

    @BatchMapping(typeName = "Order", field = "customer")
    Mono<Map<Order, CustomerView>> customer(List<Order> orders) {
        Set<String> customerIds = orders.stream()
            .map(Order::customerId)
            .collect(Collectors.toSet());

        return customers.findByIds(customerIds)
            .collectMap(CustomerView::id)
            .map(byId -> {
                Map<Order, CustomerView> result = new LinkedHashMap<>();
                for (Order order : orders) {
                    CustomerView customer = byId.get(order.customerId());
                    if (customer != null) {
                        result.put(order, customer);
                    }
                }
                return result;
            });
    }
}
```

Controller gom key và ghép kết quả với parent. `CustomerQueryService` chịu trách nhiệm truy vấn, áp dụng tenant/visibility policy và trả dữ liệu. Không đặt quy tắc nghiệp vụ như “khách hàng được nâng hạng nếu tổng chi tiêu vượt ngưỡng” trong batch method.

## 16. Xử lý authorization ở đúng tầng

Resolver có thể nhận `Principal` hoặc `@AuthenticationPrincipal` từ Spring Security. Nhưng việc lấy principal không có nghĩa mọi quyền phải được kiểm tra thủ công trong từng resolver.

Một use case có thể kiểm tra quyền ở application boundary:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CancelOrderUseCase {

    private final OrderRepository orders;

    CancelOrderUseCase(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('order:cancel')")
    @Transactional
    public OrderResult execute(String orderId, String actorId) {
        Order order = orders.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);

        if (!order.canBeManagedBy(actorId)) {
            throw new OrderNotFoundException();
        }

        order.cancel();
        return OrderResult.from(order);
    }
}
```

Method security cần được bật trong cấu hình Spring Security. Kiểm tra ownership/tenant vẫn phải áp dụng cho tài nguyên cụ thể; authority chung không tự bảo đảm người dùng có quyền trên mọi order.

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Resolver lấy actor từ principal đã xác thực rồi gọi use case. Không lấy `actorId` hoặc `tenantId` từ GraphQL argument do client tự gửi làm bằng chứng danh tính.

## 17. Xử lý lỗi nghiệp vụ ở biên GraphQL

Application/domain có thể ném exception có ý nghĩa nghiệp vụ như `OrderNotFoundException`, `OrderCannotBeCancelledException` hoặc `InsufficientStockException`. Tầng GraphQL chuyển những exception đó thành `GraphQLError` phù hợp với hợp đồng API.

Ví dụ dùng `@ControllerAdvice`:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class GraphQlBusinessExceptionHandler {

    @GraphQlExceptionHandler
    GraphQLError handle(
            InsufficientStockException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
            .errorType(ErrorType.BAD_REQUEST)
            .message("Không đủ hàng để hoàn tất đơn hàng")
            .extensions(Map.of("code", "INSUFFICIENT_STOCK"))
            .build();
    }
}
```

`@GraphQlExceptionHandler` trong `@ControllerAdvice` áp dụng cho các annotated controllers. Có thể dùng `DataFetcherExceptionResolver` cho những DataFetcher được đăng ký theo cách khác.

Không để service trả về `GraphQLError` hoặc import `GraphQlExceptionHandler`. Domain exception nên diễn đạt lỗi nghiệp vụ độc lập; GraphQL adapter quyết định message, error type, path và extension. Không trả stack trace hoặc chi tiết nội bộ cho client.

## 18. Không gọi remote service dài bên trong database transaction

Một transaction database không tự bao phủ HTTP call tới hệ thống khác. Nếu use case mở transaction rồi gọi payment gateway, email service hoặc inventory service từ xa, transaction có thể giữ connection/lock trong lúc chờ mạng và vẫn không thể rollback side effect đã xảy ra ở hệ thống ngoài.

Với nghiệp vụ cần phối hợp nhiều hệ thống, cân nhắc:

- Ghi trạng thái và outbox event trong cùng database transaction.
- Publish event sau commit qua outbox relay.
- Dùng saga/process manager cho quy trình nhiều bước và compensation.
- Dùng idempotency key để xử lý retry an toàn.
- Đặt timeout và retry policy ở integration adapter.

Không nhầm transaction local với distributed transaction. Nếu cần bảo đảm atomicity giữa nhiều hệ thống, phải thiết kế protocol và failure handling tương ứng.

## 19. Chọn transaction model phù hợp với imperative và reactive

Với Spring MVC/JPA/JDBC, `@Transactional` thường dùng transaction manager imperative, context được gắn với thread trong thời gian method được gọi qua Spring proxy.

Với Spring WebFlux và R2DBC, dùng `ReactiveTransactionManager` và reactive return type như `Mono` hoặc `Flux`. Transaction context được truyền qua Reactor Context thay vì giả định mọi callback chạy trên cùng thread.

Không mở transaction JPA imperative rồi chuyển công việc sang reactive pipeline hoặc scheduler khác và kỳ vọng transaction thread-bound tự theo sang. Không trộn blocking repository với reactive transaction mà không có thiết kế rõ ràng.

Ví dụ reactive use case:

```java
@Service
class PlaceOrderReactiveUseCase {

    private final ReactiveOrderRepository orders;

    PlaceOrderReactiveUseCase(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Mono<OrderResult> execute(PlaceOrderCommand command) {
        return validateAndCreate(command)
            .flatMap(orders::save)
            .map(OrderResult::from);
    }
}
```

Ví dụ này giả định ứng dụng đã cấu hình reactive transaction manager và các thao tác trong pipeline đều tham gia reactive transaction đó.

## 20. Kiểm thử resolver và use case riêng biệt

Phân tầng giúp chọn đúng loại test:

| Test | Thành phần | Điều cần xác minh |
|---|---|---|
| Unit test application service | Use case/domain | Quy tắc nghiệp vụ, quyết định và exception. |
| Repository integration test | Persistence | Query, constraint, mapping và transaction. |
| `@GraphQlTest` | Resolver/schema | Argument binding, gọi đúng use case, response path và error mapping. |
| End-to-end GraphQL test | Toàn ứng dụng | Security, transaction, database và GraphQL contract. |

Ví dụ test resolver với `GraphQlTester`:

```java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@GraphQlTest(OrderMutationController.class)
@WithMockUser(username = "alice")
class OrderMutationControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    PlaceOrderUseCase placeOrder;

    @Test
    void delegatesToUseCaseAndReturnsOrder() {
        given(placeOrder.execute(any(PlaceOrderCommand.class)))
            .willReturn(new PlaceOrderResult(
                "order-101", OrderStatus.PLACED, new BigDecimal("125.00")
            ));

        graphQlTester.document("""
                mutation {
                    placeOrder(input: {
                        customerId: "customer-1"
                        items: [{ productId: "product-1", quantity: 1 }]
                    }) {
                        id
                        status
                        totalAmount
                    }
                }
                """)
            .execute()
            .path("placeOrder.id")
            .entity(String.class)
            .isEqualTo("order-101");

        then(placeOrder).should().execute(any(PlaceOrderCommand.class));
    }
}
```

Test này kiểm tra resolver chuyển request tới use case và ánh xạ response. Quy tắc tồn kho, giá và transaction cần được kiểm thử trong test của `PlaceOrderUseCase`, không phải nhồi vào test GraphQL.

Các import test ở trên dùng Spring Boot 3.x và Spring Framework 6.2 trở lên. Với Spring Boot 4.x, package của `@GraphQlTest` chuyển sang `org.springframework.boot.graphql.test.autoconfigure`; `@MockitoBean` thuộc `org.springframework.test.context.bean.override.mockito`.

Test dùng `@WithMockUser` nên cần dependency `spring-security-test` ở test scope. Nếu dự án không bật Spring Security hoặc resolver không cần principal, có thể bỏ annotation này và thay bằng cơ chế cung cấp principal/context phù hợp với test.

## 21. Những dấu hiệu resolver đang chứa quá nhiều nghiệp vụ

Hãy xem lại thiết kế nếu resolver có các dấu hiệu:

- Gọi nhiều repository để tự điều phối quy trình.
- Có nhiều nhánh `if/else` thể hiện chính sách nghiệp vụ.
- Tính giá, thuế, chiết khấu hoặc commission.
- Tự thay đổi trạng thái aggregate.
- Tự mở/commit/rollback transaction.
- Gọi nhiều remote service và quyết định compensation.
- Kiểm tra quyền sở hữu bằng cách tự viết lại logic ở nhiều resolver.
- Tự định dạng business exception thành `GraphQLError` ở nhiều method.

Một resolver dài không tự động là sai nếu phần lớn code là mapping. Ngược lại, resolver ngắn nhưng gọi repository và thay đổi domain state trực tiếp vẫn có thể làm sai ranh giới trách nhiệm.

## 22. Lỗi thường gặp

**Đưa toàn bộ logic vào `@MutationMapping`.** Resolver trở thành nơi vừa xử lý transport, vừa điều phối, vừa giữ quy tắc nghiệp vụ. Tách thành application use case.

**Đặt transaction trên từng repository call.** Nhiều thao tác của một nghiệp vụ có thể commit riêng. Đặt transaction ở method đại diện cho use case cần atomicity.

**Giữ transaction cho toàn bộ GraphQL request.** Transaction có thể kéo dài qua nhiều field độc lập và giữ tài nguyên không cần thiết. Dùng transaction boundary ngắn, rõ ràng.

**Cho rằng nhiều root mutation field tự động atomic.** Tuần tự thực thi không đồng nghĩa chung transaction. Nếu nhiều bước phải cùng thành công, tạo một mutation/use case bao trọn chúng.

**Đặt invariant chỉ trong resolver.** REST, message consumer hoặc batch job có thể bỏ qua resolver. Domain/application phải bảo vệ invariant ở mọi entry point.

**Đưa `GraphQLError` vào domain/service.** Điều này khiến nghiệp vụ phụ thuộc GraphQL. Dùng domain exception và ánh xạ ở GraphQL boundary.

**Dùng nested resolver để tiếp tục transaction của mutation.** Method transaction kết thúc khi method trả về; nested field chạy sau đó không tự thuộc cùng transaction.

**Gọi remote service trong transaction dài.** Transaction local không rollback được side effect bên ngoài và có thể giữ connection lâu. Dùng outbox/saga khi cần phối hợp hệ thống.

**Trộn imperative và reactive transaction.** Transaction manager và context propagation khác nhau. Chọn model tương ứng với persistence stack.

## Kết luận

Resolver trong Spring for GraphQL nên làm nhiệm vụ adapter: nhận argument/context, gọi application use case và chuyển kết quả thành GraphQL response. Application service điều phối một nghiệp vụ và xác định transaction boundary; domain model bảo vệ invariant; repository và adapter xử lý persistence/tích hợp. Đặt transaction trên use case giúp nhiều thao tác cùng một nghiệp vụ có thể commit hoặc rollback cùng nhau, đồng thời giữ resolver độc lập với transport. Với nested field, dùng query service hoặc DataLoader; với nhiều bước phải atomic, thiết kế một mutation/use case duy nhất; với lỗi nghiệp vụ, ánh xạ exception thành GraphQL error tại biên API.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html#data.transaction)
- [Spring for GraphQL — Request Execution and Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
