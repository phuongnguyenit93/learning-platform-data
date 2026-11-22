# Mutation gọi service transaction

Trong Spring for GraphQL, GraphQL không tự định nghĩa transaction boundary cho mutation. Ứng dụng quyết định phần công việc nào phải commit hoặc rollback cùng nhau. Với kiến trúc phân lớp, cách dễ kiểm soát là để GraphQL controller nhận input rồi gọi một application service có `@Transactional`. Service tạo thành unit of work cho một nghiệp vụ, còn controller chịu trách nhiệm ánh xạ GraphQL argument và response.

Cách tổ chức này giữ transaction gắn với nghiệp vụ thay vì gắn với toàn bộ GraphQL request. Ví dụ, mutation đặt hàng có thể kiểm tra sản phẩm, giữ tồn kho và tạo đơn hàng trong cùng transaction. Nếu một bước thất bại và exception thoát khỏi service, các thay đổi cơ sở dữ liệu trong transaction được rollback theo quy tắc đã cấu hình.

Bài này đi từ schema và resolver đến service transaction, giải thích proxy của Spring, rollback, lỗi nghiệp vụ, nhiều mutation trong một request, reactive transaction và cách kiểm thử hành vi commit/rollback.

## 1. Transaction boundary nằm ở đâu?

Một GraphQL mutation thường đi qua các lớp:

~~~mermaid
flowchart TD
    A[GraphQL client] --> B[Mutation field]
    B --> C[Controller / resolver]
    C --> D[Application service proxy]
    D --> E[Begin transaction]
    E --> F[Validate business rules]
    F --> G[Repository and domain operations]
    G --> H{All steps succeed?}
    H -->|Yes| I[Commit]
    H -->|No| J[Rollback]
    I --> K[Return result to GraphQL]
    J --> L[Exception handling]
    L --> M[GraphQL errors]
~~~

Resolver là adapter giữa GraphQL và application layer. Nó nên làm các việc như nhận và bind argument, chuyển input thành command của ứng dụng, gọi application service và trả DTO hoặc kết quả phù hợp với schema.

Application service quản lý transaction và điều phối các bước nghiệp vụ. Khi controller gọi bean service qua Spring proxy, transaction interceptor mở transaction trước khi chạy method và hoàn tất transaction khi method kết thúc.

Không cần mở một transaction bao quanh toàn bộ GraphQL request chỉ để xử lý một mutation. Một request có thể có nhiều field độc lập, trong khi transaction thường nên bao quanh một nghiệp vụ có ranh giới rõ ràng.

## 2. GraphQL schema cho mutation đặt hàng

Ví dụ schema khai báo input và kết quả:

~~~graphql
input PlaceOrderInput {
    productId: ID!
    quantity: Int!
}

type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}

type Order {
    id: ID!
    status: String!
    quantity: Int!
    customer: Customer
    items: [OrderItem!]!
}

type Customer {
    id: ID!
    name: String!
}

type OrderItem {
    productName: String!
    quantity: Int!
}
~~~

GraphQL kiểm tra cấu trúc document, tên field, kiểu argument và nullability trước khi gọi resolver. Những lỗi như thiếu `input`, truyền sai scalar hoặc dùng field không tồn tại có thể bị từ chối trước khi transaction service bắt đầu.

Schema không tự xác định cách commit dữ liệu. Nó chỉ mô tả operation và kiểu dữ liệu mà client có thể gửi hoặc nhận.

## 3. Input và DTO của ứng dụng

Tách GraphQL input khỏi command nội bộ giúp application layer không phụ thuộc vào schema:

~~~java
public record PlaceOrderInput(
    String productId,
    Integer quantity
) {
}

public record PlaceOrderCommand(
    String productId,
    int quantity
) {
}

public record OrderView(
    String id,
    String status,
    int quantity
) {
}
~~~

Các record chỉ minh họa kiểu dữ liệu. Trong dự án thực tế, `PlaceOrderInput` thường thuộc GraphQL adapter; `PlaceOrderCommand` và `OrderView` thuộc application layer. Package/import được lược bỏ ở đoạn khai báo DTO để tập trung vào ranh giới giữa các lớp.

GraphQL input có thể chứa wrapper type như `Integer` để phản ánh quá trình binding và validation. Command nội bộ có thể dùng primitive hoặc kiểu domain phù hợp sau khi input đã được kiểm tra.

Không nên truyền thẳng entity JPA làm input hoặc response chỉ vì nó có các field tương tự schema. Entity là mô hình persistence; DTO là hợp đồng trả về của API. Tách chúng giúp tránh lộ cột nội bộ, lazy-loading ngoài transaction và thay đổi schema làm ảnh hưởng persistence model.

## 4. Controller chỉ điều phối GraphQL

Resolver gọi service và trả kết quả:

~~~java
package com.example.orders.graphql;

import com.example.orders.application.OrderApplicationService;
import com.example.orders.application.PlaceOrderCommand;
import com.example.orders.application.OrderView;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMutationController {

    private final OrderApplicationService orderService;

    public OrderMutationController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public OrderView placeOrder(@Argument("input") PlaceOrderInput input) {
        PlaceOrderCommand command = new PlaceOrderCommand(
            input.productId(),
            input.quantity()
        );

        return orderService.placeOrder(command);
    }
}
~~~

Controller không cần tự gọi `PlatformTransactionManager` hoặc mở transaction thủ công. Spring inject bean `OrderApplicationService`; lời gọi đi qua proxy nếu transaction management được cấu hình và method được đánh dấu phù hợp.

Có thể đặt `@Transactional` trực tiếp trên method `@MutationMapping`, nhưng service layer thường là ranh giới phù hợp hơn: cùng nghiệp vụ có thể được gọi từ GraphQL, REST, message consumer hoặc batch job mà vẫn dùng chung transaction policy.

Tài liệu Spring for GraphQL trình bày `@Transactional` ngay trên `@MutationMapping` như cách đơn giản để tạo transaction per controller method. Bài này dùng service boundary vì mutation đang ủy quyền nghiệp vụ cho application service và cùng service có thể được gọi từ adapter khác. Hai cách đều hợp lệ. Nếu cả controller và service cùng được đánh dấu `@Transactional` với propagation mặc định `REQUIRED`, lời gọi service sẽ tham gia transaction đã mở ở controller; không cần đánh dấu cả hai chỉ để có rollback.

## 5. Đặt @Transactional trên application service

Ví dụ service tạo đơn hàng:

~~~java
package com.example.orders.application;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    public OrderApplicationService(
            ProductRepository productRepository,
            OrderRepository orderRepository,
            InventoryService inventoryService) {
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public OrderView placeOrder(PlaceOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be positive");
        }

        Product product = productRepository.findById(command.productId())
            .orElseThrow(() ->
                new ProductNotFoundException(command.productId())
            );

        Order order = Order.createPending(product, command.quantity());
        Order saved = orderRepository.save(order);

        inventoryService.reserve(product.getId(), command.quantity());
        saved.confirm();

        return new OrderView(
            saved.getId().toString(),
            saved.getStatus().name(),
            saved.getQuantity()
        );
    }
}
~~~

Khi `placeOrder` được gọi qua proxy:

1. Spring chọn transaction manager phù hợp.
2. Transaction bắt đầu hoặc tham gia transaction hiện có.
3. Các thao tác repository dùng cùng transaction manager sẽ tham gia transaction đó.
4. Nếu method hoàn tất bình thường, transaction được commit.
5. Nếu exception phù hợp với rollback rule thoát khỏi method, transaction được rollback.

Mặc định propagation là `REQUIRED`: nếu đã có transaction phù hợp, method tham gia transaction đó; nếu chưa có, Spring tạo transaction mới.

Các repository và service cần dùng chung transaction manager và resource phù hợp thì mới cùng nằm trong một transaction cơ sở dữ liệu. Hai database độc lập hoặc một lời gọi HTTP tới dịch vụ khác không tự động trở thành một transaction nguyên tử.

## 6. Vì sao service layer là transaction boundary tốt?

Transaction nên bao trọn một nghiệp vụ hoàn chỉnh. Ví dụ đặt hàng có thể gồm kiểm tra sản phẩm còn hoạt động, kiểm tra số lượng hợp lệ, giữ tồn kho, tạo đơn hàng và các dòng đơn hàng, ghi nhận trạng thái ban đầu.

Nếu mỗi repository method tự mở transaction riêng, một bước có thể commit trong khi bước sau thất bại. Khi toàn bộ chuỗi nằm trong một service transaction, các thao tác tham gia cùng transaction có thể commit hoặc rollback như một unit of work.

Một method service cũng dễ được tái sử dụng hơn transaction gắn trực tiếp với GraphQL controller. Nếu mai sau có REST endpoint hoặc message handler gọi cùng nghiệp vụ, transaction policy không bị lặp lại ở từng adapter.

Không nên đặt transaction ở một service quá rộng chỉ để giữ kết nối cơ sở dữ liệu trong suốt một request. Hãy chọn method đại diện cho hành động nghiệp vụ cụ thể.

## 7. Proxy Spring và self-invocation

`@Transactional` dựa trên Spring AOP proxy trong cấu hình mặc định. Lời gọi phải đi qua proxy thì transaction advice mới được áp dụng.

~~~mermaid
flowchart LR
    A[GraphQL controller] -->|Bean reference| B[Spring proxy]
    B --> C[Transaction interceptor]
    C --> D[OrderApplicationService]
    D --> E[Repository]
~~~

Lời gọi từ controller tới bean service được Spring inject thường đi qua proxy. Nhưng lời gọi nội bộ từ một method sang method khác trong cùng object không đi qua proxy:

~~~java
@Service
public class OrderApplicationService {

    public OrderView placeOrder(PlaceOrderCommand command) {
        return createOrder(command); // self-invocation
    }

    @Transactional
    public OrderView createOrder(PlaceOrderCommand command) {
        // ...
    }
}
~~~

Trong ví dụ này, lời gọi `createOrder` là self-invocation. Với proxy mode mặc định, annotation trên method được gọi nội bộ không tạo transaction mới.

Thiết kế rõ ràng hơn là đặt `@Transactional` trên method public của service được gọi từ bean khác, hoặc tách một collaborator thành bean riêng nếu thật sự cần transaction boundary độc lập. Tránh tự inject chính service để gọi lại proxy chỉ nhằm vượt qua self-invocation.

## 8. Quy tắc rollback mặc định

Spring mặc định đánh dấu rollback khi method transactional kết thúc bằng `RuntimeException` hoặc `Error`. Checked exception không tự động gây rollback theo mặc định.

Ví dụ business exception không cần khai báo thêm nếu nó kế thừa `RuntimeException`:

~~~java
public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String productId) {
        super("Insufficient stock for product " + productId);
    }
}
~~~

Nếu nghiệp vụ dùng checked exception, khai báo rõ rollback rule:

~~~java
@Transactional(rollbackFor = PaymentDeclinedException.class)
public OrderView placeOrder(PlaceOrderCommand command)
        throws PaymentDeclinedException {
    // ...
}
~~~

Có thể dùng `noRollbackFor` cho trường hợp đặc biệt, nhưng phải chắc rằng việc commit khi exception xảy ra đúng với nghiệp vụ.

Đừng giả định mọi GraphQL error đều làm transaction rollback. Transaction manager quyết định rollback dựa trên exception thoát khỏi transactional method và rollback rules, không dựa trên việc response GraphQL có field `errors` hay không.

## 9. Không nuốt exception nếu cần rollback

Nếu service bắt exception rồi tiếp tục trả về bình thường, transaction interceptor có thể commit:

~~~java
@Transactional
public OrderView placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(Order.pending(command));

    try {
        inventoryService.reserve(command.productId(), command.quantity());
    } catch (InsufficientStockException exception) {
        return new OrderView(
            order.getId().toString(),
            "REJECTED",
            order.getQuantity()
        );
    }

    return new OrderView(
        order.getId().toString(),
        "CREATED",
        order.getQuantity()
    );
}
~~~

Đoạn code trên trả về bình thường sau khi bắt lỗi. Nếu exception không được ném ra ngoài và transaction không được đánh dấu rollback-only, thao tác lưu đơn có thể được commit.

Có một nuance quan trọng: nếu `inventoryService.reserve` là method được proxy với `@Transactional(propagation = REQUIRED)` và ném `RuntimeException`, transaction interceptor bên trong có thể đánh dấu transaction đang dùng là rollback-only trước khi exception tới khối `catch`. Khi method bên ngoài trả về, bước commit sẽ phát sinh `UnexpectedRollbackException` và dữ liệu vẫn rollback. Vì vậy, kết quả phụ thuộc việc transaction đã bị đánh dấu rollback-only hay chưa, không chỉ phụ thuộc việc exception có bị catch hay không.

Nếu lỗi phải hủy toàn bộ nghiệp vụ, hãy để exception thoát khỏi method hoặc đánh dấu rollback-only một cách có chủ đích. Thông thường nên ném business exception rồi chuyển nó thành GraphQL error ở lớp xử lý lỗi.

Nếu business outcome là kết quả bình thường, ví dụ từ chối đơn vì hết hàng và không có dữ liệu nào cần lưu, có thể trả payload nghiệp vụ. Nhưng nếu đã ghi dữ liệu trước đó và muốn hủy các thay đổi, cần quy định rollback rõ ràng thay vì chỉ trả một payload báo lỗi.

## 10. Chuyển business exception thành GraphQL error

Spring for GraphQL cho phép xử lý exception từ data fetcher bằng `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler`.

Ví dụ dùng controller advice:

~~~java
package com.example.orders.graphql;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlBusinessExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleInsufficientStock(
            GraphqlErrorBuilder<?> errorBuilder,
            InsufficientStockException exception) {

        return errorBuilder
            .errorType(ErrorType.BAD_REQUEST)
            .message("Không đủ hàng để hoàn tất đơn")
            .build();
    }
}
~~~

Exception được ném từ service đi qua transaction proxy trước. Transaction interceptor áp dụng rollback rule rồi truyền exception ra controller invocation; sau đó GraphQL exception handler có thể chuyển exception thành lỗi trong response.

Không trả stack trace, câu SQL, tên bảng, thông tin credential hoặc dữ liệu cá nhân trong GraphQL error message. Client chỉ cần message và error code ổn định để xử lý. Log nội bộ có thể ghi chi tiết hơn nhưng cần kiểm soát dữ liệu nhạy cảm.

Nếu dùng payload kiểu `OrderResult` có `userErrors`, hãy xác định rõ lỗi đó là business outcome bình thường hay yêu cầu rollback. Một response có `userErrors` tự nó không đánh dấu transaction rollback.

## 11. Validation trước và trong transaction

Có hai lớp validation:

- GraphQL validation/coercion kiểm tra document, scalar, argument và input type trước khi gọi resolver.
- Business validation kiểm tra trạng thái domain như tồn kho, giới hạn mua, quyền sở hữu hoặc trạng thái đơn hàng.

Các kiểm tra thuần túy trên input có thể thực hiện trước khi ghi dữ liệu. Những kiểm tra phụ thuộc trạng thái cơ sở dữ liệu nên nằm trong application service và chạy trong transaction khi cần tính nhất quán.

Ví dụ:

~~~java
@Transactional
public OrderView placeOrder(PlaceOrderCommand command) {
    if (command.quantity() < 1 || command.quantity() > 20) {
        throw new InvalidOrderException("Quantity is outside allowed range");
    }

    Product product = productRepository.findById(command.productId())
        .orElseThrow(() -> new ProductNotFoundException(command.productId()));

    if (!product.isOrderable()) {
        throw new ProductUnavailableException(command.productId());
    }

    // Reserve stock and persist the order.
}
~~~

Validation trước khi ghi giúp tránh công việc thừa. Tuy nhiên, kiểm tra số lượng tồn kho và cập nhật tồn kho phải được thiết kế chống race condition, ví dụ bằng optimistic/pessimistic locking hoặc câu lệnh cập nhật có điều kiện. Chỉ mở transaction không tự ngăn hai request đồng thời cùng đọc một số lượng tồn kho rồi cùng đặt hàng.

## 12. Nested field được resolve sau transaction của mutation

Giả sử mutation trả về `Order`, rồi client yêu cầu thêm `customer` và `items`:

~~~graphql
mutation {
    placeOrder(input: { productId: "p-1", quantity: 2 }) {
        id
        status
        customer {
            id
            name
        }
        items {
            productName
            quantity
        }
    }
}
~~~

Nếu transaction chỉ nằm trong `OrderApplicationService.placeOrder`, transaction kết thúc khi service method trả về. GraphQL sau đó có thể tiếp tục resolve nested field như `customer` và `items`.

Không giả định nested resolver tự động chạy trong transaction của mutation root. Nếu nested resolver cần đọc dữ liệu, nó có thể dùng một service đọc riêng, với transaction/read-only policy phù hợp. Cần cân nhắc tính nhất quán nếu dữ liệu thay đổi giữa lúc mutation commit và lúc nested field được đọc.

Với JPA, tránh trả entity chứa lazy relationship rồi để GraphQL đọc quan hệ sau khi persistence context đã đóng. Có thể trả DTO chứa những field đã tải trong transaction, dùng projection hoặc query fetch đúng dữ liệu cần trả, dùng nested resolver đọc dữ liệu riêng qua application service, hoặc dùng `@BatchMapping`/DataLoader để gom các lần đọc quan hệ.

Không giữ transaction mở chỉ để tránh thiết kế DTO hoặc resolver phù hợp.

## 13. Nhiều mutation field trong một GraphQL request

GraphQL cho phép một operation có nhiều top-level mutation field. Theo execution semantics, các field mutation cấp cao nhất được thực thi tuần tự theo thứ tự trong document. Nhưng tuần tự không có nghĩa chúng tự động dùng chung một transaction.

Ví dụ:

~~~graphql
mutation {
    reserveStock(productId: "p-1", quantity: 2) {
        success
    }
    createShipment(orderId: "o-9") {
        id
    }
}
~~~

Nếu mỗi resolver gọi một service method `@Transactional` riêng và không có transaction bao ngoài, mỗi service invocation có transaction riêng. `reserveStock` có thể commit trước khi `createShipment` chạy. Nếu field thứ hai thất bại, transaction của field thứ nhất không tự rollback.

Nếu hai hành động phải nguyên tử, nên thiết kế một mutation đại diện cho cả use case:

~~~graphql
input FulfillOrderInput {
    orderId: ID!
    warehouseId: ID!
}

type Mutation {
    fulfillOrder(input: FulfillOrderInput!): Fulfillment!
}
~~~

Resolver gọi một application service `fulfillOrder` duy nhất. Service thực hiện giữ hàng, tạo shipment và cập nhật trạng thái trong một transaction. Đây là cách đơn giản để bảo đảm cả chuỗi cùng commit hoặc rollback.

Chỉ dùng transaction bao trùm toàn bộ GraphQL request khi thật sự có yêu cầu rõ ràng và hiểu các hệ quả về concurrency, thread model và thời gian giữ resource.

## 14. Transaction per mutation method và transaction toàn request

Spring for GraphQL mô tả hai chiến lược tổng quát:

| Chiến lược | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| Transaction per controller/service method | Mỗi method có ranh giới riêng | Phần lớn mutation nghiệp vụ |
| Transaction bao toàn GraphQL execution | Nhiều data fetcher cùng tham gia một transaction | Use case đặc biệt cần một unit of work cấp request |

Transaction toàn request phức tạp hơn. Với transaction đồng bộ dựa trên JDBC/JPA, Spring thường gắn transaction vào thread. Muốn nhiều data fetcher tham gia cùng transaction, execution strategy phải bảo đảm các invocation chạy tuần tự trên cùng thread. GraphQL thông thường có thể thực thi các field query song song; việc ép toàn bộ execution tuần tự có thể giảm concurrency và kéo dài transaction.

Giữ transaction qua nhiều resolver còn có thể giữ connection và lock lâu hơn cần thiết. Vì vậy, transaction per mutation method/service là lựa chọn mặc định dễ kiểm soát hơn.

## 15. Propagation và nhiều service cùng tham gia

Giá trị propagation mặc định của `@Transactional` là `REQUIRED`.

~~~java
@Service
public class OrderApplicationService {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    @Transactional
    public OrderView placeOrder(PlaceOrderCommand command) {
        inventoryService.reserve(command.productId(), command.quantity());

        Order order = orderRepository.save(Order.create(command));
        return OrderView.from(order);
    }
}
~~~

Nếu `InventoryService.reserve` cũng có `@Transactional` với propagation `REQUIRED` và dùng cùng transaction manager, method đó tham gia transaction hiện có. Nếu lưu đơn thất bại sau khi giữ hàng trong cùng database transaction, thay đổi tồn kho cũng được rollback.

Một số propagation khác:

- `REQUIRES_NEW`: tạm treo transaction hiện tại và tạo transaction độc lập. Dữ liệu trong transaction mới có thể commit ngay cả khi transaction ngoài rollback.
- `MANDATORY`: yêu cầu phải có transaction hiện tại.
- `SUPPORTS`: tham gia transaction nếu có, nếu không thì chạy không có transaction.
- `NOT_SUPPORTED`: tạm treo transaction hiện tại để chạy không có transaction.

Không dùng `REQUIRES_NEW` chỉ để tránh lỗi transaction. Nó thay đổi tính nguyên tử: dữ liệu đã commit trong transaction độc lập không tự rollback cùng transaction ngoài.

Nếu có nhiều transaction manager, chỉ định rõ manager cho service cần dùng:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public OrderView placeOrder(PlaceOrderCommand command) {
    // ...
}
~~~

Đảm bảo repository và các collaborator ghi dữ liệu dùng đúng manager/resource mà nghiệp vụ dự kiến.

## 16. Reactive mutation và ReactiveTransactionManager

Nếu service trả về reactive type như `Mono` hoặc `Flux`, Spring có thể áp dụng reactive transaction management khi có `ReactiveTransactionManager` phù hợp.

~~~java
@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;

    public ReactiveOrderService(ReactiveOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Mono<OrderView> placeOrder(PlaceOrderCommand command) {
        return validate(command)
            .then(orderRepository.save(Order.pending(command)))
            .map(OrderView::from);
    }
}
~~~

Reactive transaction được gắn với Reactor Context, không dựa vào thread-local như transaction JDBC thông thường. Các thao tác dữ liệu tham gia transaction cần nằm trong cùng reactive pipeline và dùng reactive resource/transaction manager tương ứng.

Không gọi `subscribe()` bên trong service để khởi chạy một pipeline tách rời. Không `block()` để chuyển reactive pipeline thành thao tác đồng bộ. Hãy trả publisher về cho GraphQL runtime để pipeline được subscribe và quản lý đúng lifecycle.

Nếu method trả `Mono` nhưng repository dùng JDBC/JPA imperative, không tự động biến transaction JDBC thành reactive transaction. Chọn đúng programming model và transaction manager cho loại resource đang sử dụng.

## 17. @Transactional với CompletableFuture

Cần phân biệt reactive publisher với `CompletableFuture`. Spring nhận diện `Publisher`/Reactor types cho reactive transaction management. Một method imperative trả `CompletableFuture` không đồng nghĩa transaction thread-bound sẽ chờ future hoàn tất.

~~~java
@Transactional
public CompletableFuture<OrderView> placeOrderAsync(PlaceOrderCommand command) {
    return CompletableFuture.supplyAsync(() -> {
        // JDBC work may run after the method has returned.
        return repository.save(Order.create(command));
    });
}
~~~

Ví dụ trên không phải cách an toàn để giữ JDBC transaction quanh phần công việc chạy bất đồng bộ. Method trả future ngay; transaction imperative có thể kết thúc khi method trả về, trước khi phần lambda chạy xong.

Từ Spring Framework 6.1, một `Future` đã hoàn tất với trạng thái lỗi ngay tại thời điểm method trả về cũng có thể kích hoạt rollback. Điều này không có nghĩa transaction imperative sẽ chờ một future còn đang chạy rồi mới commit.

Với JDBC/JPA, giữ các thao tác trong cùng lời gọi đồng bộ qua transaction proxy hoặc thiết kế một worker/service có transaction riêng. Với reactive database access, dùng `Mono`/`Flux` và `ReactiveTransactionManager` xuyên suốt pipeline. Đừng suy luận rằng mọi kiểu return bất đồng bộ đều được transaction interceptor chờ tới completion.

## 18. Gọi dịch vụ ngoài và transactional outbox

Transaction cơ sở dữ liệu chỉ bảo đảm atomicity cho resource được transaction manager quản lý. Nó không tự rollback một HTTP request đã gửi, một email đã gửi hoặc một message đã được broker nhận.

Ví dụ, nếu service cập nhật database rồi gọi payment provider qua HTTP, database rollback không thể hoàn tác khoản thanh toán đã được provider chấp nhận.

Một số hướng thiết kế:

- Giữ transaction database ngắn và thực hiện các lời gọi ngoài ở bước orchestration phù hợp.
- Dùng idempotency key khi gọi API ngoài để xử lý retry an toàn.
- Dùng transactional outbox: ghi business change và event cần phát vào cùng database transaction; một publisher riêng đọc outbox rồi gửi message.
- Dùng saga/compensation khi nghiệp vụ trải qua nhiều service và cần hành động bù.

`@TransactionalEventListener(phase = org.springframework.transaction.event.TransactionPhase.AFTER_COMMIT)` có thể chạy listener sau khi transaction commit. Tuy nhiên, listener trong bộ nhớ không thay thế durable outbox nếu cần bảo đảm event không bị mất khi process dừng ngay sau commit.

## 19. Kiểm thử transaction của mutation

`@GraphQlTest` phù hợp để kiểm tra GraphQL controller gọi đúng service và response có đúng shape. Vì service thường được mock trong slice test, nó không chứng minh repository thật đã commit hoặc rollback.

Để kiểm tra transaction, dùng integration test với `@SpringBootTest`, GraphQL tester và database test phù hợp. Ví dụ kiểm tra service rollback sau khi một bước nghiệp vụ thất bại:

Với `HttpGraphQlTester`, thêm `spring-graphql-test` trong test scope và `spring-boot-starter-webflux` trong test scope nếu ứng dụng chưa có WebFlux trên classpath. Spring Boot có thể tự cấu hình tester cho integration test; package của `@AutoConfigureHttpGraphQlTester` khác nhau giữa Boot 3 và Boot 4 như ghi chú trong ví dụ.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

// Spring Boot 4.x package. In Boot 3.x use
// org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester.
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class OrderMutationTransactionTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void rollsBackOrderWhenInventoryReservationFails() {
        long before = orderRepository.count();

        graphQlTester.document("""
                mutation {
                    placeOrder(input: {
                        productId: "out-of-stock"
                        quantity: 3
                    }) {
                        id
                    }
                }
                """)
            .execute()
            .errors()
            .expect(error ->
                error.getMessage().contains("Không đủ hàng")
            )
            .verify();

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

Ví dụ giả định test database có fixture sản phẩm `out-of-stock` với lượng tồn nhỏ hơn 3, service lưu một phần dữ liệu rồi ném `InsufficientStockException`, và exception handler chuyển exception thành GraphQL error. Test method không gắn `@Transactional`, để transaction của service thực sự commit hoặc rollback độc lập trước khi assertion đọc database.

Các test quan trọng khác gồm thành công: đơn hàng được lưu và trạng thái đúng; business exception: không có dữ liệu dở dang sau rollback; checked exception: rollback đúng khi có `rollbackFor`; nhiều service cùng `REQUIRED`: các thao tác cùng rollback; nhiều mutation field: xác minh mỗi service invocation có transaction boundary dự kiến; external side effect: xác minh outbox/event được ghi cùng transaction.

## 20. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Dữ liệu đã lưu dù mutation trả GraphQL error | Exception bị bắt và service trả bình thường | Ném lại exception hoặc đánh dấu rollback-only |
| Method có `@Transactional` nhưng không rollback | Self-invocation hoặc bean không đi qua proxy | Gọi method qua bean proxy từ collaborator khác |
| Checked exception nhưng dữ liệu vẫn commit | Mặc định checked exception không rollback | Khai báo `rollbackFor` |
| Hai mutation field chạy tuần tự nhưng field sau lỗi không hoàn tác field trước | Mỗi service call có transaction riêng | Tạo mutation orchestration cho nghiệp vụ cần atomicity |
| Nested field không đọc được lazy relationship | Transaction của mutation service đã kết thúc | Trả DTO/projection hoặc dùng resolver đọc riêng |
| Hai request cùng đặt sản phẩm cuối | Transaction không tự giải quyết race condition | Dùng locking hoặc cập nhật có điều kiện |
| HTTP payment đã thành công nhưng database rollback | HTTP service không thuộc DB transaction | Idempotency, outbox, saga hoặc compensation |
| Reactive transaction không bao quanh thao tác DB | Dùng sai transaction manager hoặc pipeline bị tách | Dùng ReactiveTransactionManager và giữ cùng Reactor pipeline |
| JDBC transaction kết thúc trước async task | Method trả CompletableFuture ngay | Không coi future là reactive transaction; đặt transaction trong worker |
| Test không phát hiện rollback sai | Test method tự mở transaction hoặc chỉ mock service | Dùng integration test quan sát commit/rollback thực |

## 21. Checklist triển khai

- Resolver chỉ bind input và gọi application service?
- Transaction boundary đại diện cho một nghiệp vụ hoàn chỉnh?
- Method `@Transactional` được gọi qua Spring proxy?
- Các repository dùng cùng transaction manager khi cần atomicity?
- Rollback rule phù hợp với business exception?
- Exception không bị nuốt trước khi transaction interceptor xử lý?
- GraphQL exception handler chỉ chuyển lỗi thành response sau khi service đã kết thúc?
- Nested field không phụ thuộc lazy entity sau khi transaction đóng?
- Nhiều mutation field có transaction policy rõ ràng?
- Nghiệp vụ cần atomicity nhiều bước có một mutation orchestration phù hợp?
- Reactive service dùng đúng `ReactiveTransactionManager` và Reactor pipeline?
- Lời gọi HTTP/message/email có chiến lược outbox hoặc compensation khi cần?
- Integration test xác minh cả commit và rollback với database thật/test container?

Mutation là điểm vào của một command từ phía client, còn application service là nơi phù hợp để đặt transaction cho nghiệp vụ. Hãy để resolver gọi service qua Spring proxy, gom các thao tác persistence liên quan vào một transaction và để rollback rule xử lý exception theo đúng ý nghĩa nghiệp vụ. Nhiều mutation field trong cùng request vẫn có thể thuộc nhiều transaction riêng; nếu cần một kết quả nguyên tử, hãy thiết kế một mutation orchestration duy nhất. Với reactive access, dùng Reactor transaction đúng cách; với side effect ngoài database, dùng outbox hoặc cơ chế bù thay vì kỳ vọng `@Transactional` bao trùm mọi hệ thống.

## Tài liệu tham khảo

- [Spring for GraphQL — Data Integration and Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [GraphQL Java — Execution Strategies](https://graphql-java.com/documentation/execution/)




