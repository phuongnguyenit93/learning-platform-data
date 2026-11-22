# Mutation transaction

GraphQL Mutation dùng để thay đổi dữ liệu hoặc trạng thái của hệ thống. Một mutation thực tế thường gồm nhiều bước liên quan: kiểm tra dữ liệu đầu vào, đọc trạng thái hiện tại, kiểm tra điều kiện nghiệp vụ, ghi một hoặc nhiều bản ghi và tạo kết quả trả về. Nếu một bước ghi thành công nhưng bước tiếp theo thất bại, dữ liệu có thể rơi vào trạng thái không nhất quán. **Database transaction** giúp nhóm các thao tác thuộc cùng một nghiệp vụ thành một đơn vị nguyên tử: tất cả cùng commit hoặc cùng rollback.

Trong Spring for GraphQL, annotation **@MutationMapping** chỉ ánh xạ một field của Mutation root tới phương thức Java. Nó không tự mở transaction. Muốn bảo đảm nhiều thao tác lưu trữ được thực hiện trong cùng một transaction, ứng dụng thường đặt ranh giới transaction ở service method và dùng **@Transactional** của Spring.

## Mutation và transaction giải quyết hai vấn đề khác nhau

GraphQL định nghĩa cách client yêu cầu server thực hiện một thao tác thay đổi dữ liệu. Database transaction định nghĩa cách hệ thống bảo đảm tính nhất quán khi thực hiện các thao tác lưu trữ. Hai khái niệm phối hợp với nhau nhưng không thay thế nhau:

- **@MutationMapping** xác định phương thức xử lý field mutation.
- Service điều phối use case và gọi repository hoặc hệ thống dữ liệu.
- **@Transactional** xác định phạm vi transaction do Spring quản lý.
- Transaction manager điều phối commit hoặc rollback đối với tài nguyên mà nó quản lý.

Ví dụ một thao tác đặt hàng cần giảm tồn kho và tạo đơn hàng. Hai thay đổi này phải cùng thành công. Nếu tồn kho đã giảm nhưng việc tạo đơn hàng thất bại, transaction cần rollback để tồn kho trở về trạng thái ban đầu.

## GraphQL thực thi mutation theo thứ tự tuần tự

Theo quy tắc thực thi GraphQL, các field cấp cao nhất trong một Mutation operation được thực thi tuần tự theo thứ tự xuất hiện trong selection set. Quy tắc này giúp những mutation field trong cùng operation không chạy đồng thời với nhau.

Ví dụ client gửi:

~~~graphql
mutation {
  reserve: reserveStock(productId: "p-10", quantity: 2) {
    id
  }
  create: createOrder(productId: "p-10", quantity: 2) {
    id
  }
}
~~~

Field reserveStock được thực thi trước createOrder. Tuy nhiên, **thực thi tuần tự không đồng nghĩa toàn bộ operation tự động nằm trong một database transaction**. Nếu mỗi resolver gọi một service có transaction riêng, transaction của field thứ nhất có thể commit trước khi field thứ hai bắt đầu. Nếu field thứ hai thất bại, transaction đã commit của field thứ nhất không tự rollback.

Vì vậy, nên thiết kế một mutation field đại diện cho một use case nghiệp vụ hoàn chỉnh. Nếu đặt hàng cần kiểm tra tồn kho, giảm tồn kho và tạo đơn, hãy đưa các bước đó vào cùng một service method có transaction thay vì yêu cầu client gọi nhiều mutation field để tự phối hợp quy trình.

## Định nghĩa schema cho một mutation nghiệp vụ

Ví dụ schema cho thao tác đặt hàng:

~~~graphql
type Query {
  order(id: ID!): Order
}

type Mutation {
  placeOrder(input: PlaceOrderInput!): OrderReceipt!
}

input PlaceOrderInput {
  productId: ID!
  quantity: Int!
  requestId: ID!
}

type OrderReceipt {
  orderId: ID!
  productId: ID!
  quantity: Int!
  status: String!
}

type Order {
  id: ID!
  status: String!
}
~~~

PlaceOrderInput gom dữ liệu đầu vào của use case. requestId có thể được dùng làm khóa idempotency để nhận diện yêu cầu lặp lại. OrderReceipt là output DTO mô tả kết quả đã được tạo. Output DTO giúp controller trả dữ liệu cần thiết mà không phụ thuộc vào entity persistence hoặc quan hệ lazy của ORM.

Mutation operation của client:

~~~graphql
mutation PlaceOrder($input: PlaceOrderInput!) {
  placeOrder(input: $input) {
    orderId
    productId
    quantity
    status
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "productId": "p-10",
    "quantity": 2,
    "requestId": "req-2025-0001"
  }
}
~~~

## Đặt ranh giới transaction ở service

Một service method nên bao trọn các thao tác dữ liệu cần thành công hoặc thất bại cùng nhau. Ví dụ:

~~~java
@Service
public class OrderService {

    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;

    public OrderService(
            ProductRepository productRepository,
            OrderRepository orderRepository) {
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderReceipt placeOrder(PlaceOrderInput input) {
        Product product = productRepository.findById(input.productId())
                .orElseThrow(() -> new ProductNotFoundException(input.productId()));

        if (input.quantity() <= 0) {
            throw new InvalidOrderException("Số lượng phải lớn hơn 0");
        }

        if (product.getAvailableQuantity() < input.quantity()) {
            throw new InsufficientStockException(product.getId());
        }

        product.decreaseAvailableQuantity(input.quantity());

        Order order = Order.create(
                product.getId(),
                input.quantity(),
                OrderStatus.CREATED);

        Order savedOrder = orderRepository.save(order);

        return new OrderReceipt(
                savedOrder.getId(),
                product.getId(),
                input.quantity(),
                savedOrder.getStatus().name());
    }
}
~~~

Khi phương thức placeOrder được gọi qua Spring transaction proxy, Spring bắt đầu transaction trước khi thực thi phần thân phương thức. Các thao tác repository tham gia cùng transaction manager. Nếu phương thức kết thúc bình thường, transaction được commit. Nếu exception phù hợp với rollback rule thoát khỏi phương thức, transaction được rollback.

Controller chỉ cần chuyển input tới service:

~~~java
@Controller
public class OrderMutationController {

    private final OrderService orderService;

    public OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public OrderReceipt placeOrder(@Argument PlaceOrderInput input) {
        return orderService.placeOrder(input);
    }
}
~~~

@MutationMapping không cần tự quản lý commit hoặc rollback. Transaction boundary nằm ở OrderService.placeOrder, nơi có đủ ngữ cảnh nghiệp vụ để xác định những thao tác nào cần nguyên tử.

## Transaction được mở và kết thúc khi nào?

Với transaction quản lý theo kiểu imperative, Spring thường thực hiện các bước:

1. Lời gọi đi qua proxy được tạo bởi transaction infrastructure.
2. Transaction manager bắt đầu transaction hoặc tham gia transaction hiện có theo propagation.
3. Service thực thi các thao tác đọc và ghi.
4. Nếu phương thức trả về bình thường, Spring commit transaction.
5. Nếu exception kích hoạt rollback rule thoát khỏi phương thức, Spring rollback transaction rồi chuyển exception tiếp tục lên tầng gọi.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant G as GraphQL Runtime
    participant R as Mutation Resolver
    participant S as Order Service
    participant T as Transaction Manager
    participant DB as Database

    C->>G: mutation placeOrder
    G->>R: Gọi resolver
    R->>S: placeOrder(input)
    S->>T: Bắt đầu transaction
    T->>DB: Mở transaction
    S->>DB: Đọc sản phẩm và tồn kho
    S->>DB: Cập nhật tồn kho
    S->>DB: Lưu đơn hàng
    S->>T: Kết thúc method
    T->>DB: Commit
    S-->>R: OrderReceipt
    R-->>G: Kết quả field
    G-->>C: GraphQL response
~~~

Nếu thao tác lưu đơn hàng phát sinh exception trước khi service kết thúc, nhánh xử lý sẽ là rollback thay cho commit. Transaction manager chỉ điều phối các tài nguyên đã được cấu hình và tham gia transaction của nó; không nên giả định mọi hệ thống bên ngoài đều tự động nằm trong cùng transaction.

## Quy tắc rollback mặc định

Với @Transactional của Spring, mặc định transaction rollback khi phương thức kết thúc bằng RuntimeException hoặc Error. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

Ví dụ yêu cầu rollback cả checked exception:

~~~java
@Transactional(rollbackFor = Exception.class)
public OrderReceipt placeOrder(PlaceOrderInput input) throws OrderProcessingException {
    // Các thao tác đọc và ghi thuộc cùng transaction
}
~~~

Có thể dùng noRollbackFor cho loại exception không muốn rollback, nhưng cần cân nhắc kỹ vì điều đó có thể khiến một phần thay đổi được commit dù nghiệp vụ báo lỗi.

Các điểm cần lưu ý:

- Exception phải thoát khỏi transaction boundary để interceptor áp dụng rollback rule.
- Nếu code bắt exception rồi bỏ qua và trả kết quả bình thường, Spring thường commit transaction.
- Nếu cần đánh dấu rollback trong trường hợp đã bắt exception, có thể dùng cơ chế rollback-only; nên ưu tiên để exception phù hợp truyền qua boundary khi thiết kế cho phép.
- Validation nên thực hiện trước khi ghi dữ liệu để tránh mở rộng phạm vi thay đổi không cần thiết.

## Lỗi GraphQL và rollback database không phải một khái niệm

GraphQL response có thể chứa cả data và errors. Việc response có errors không tự chứng minh transaction đã rollback. Transaction quyết định commit hay rollback dựa trên cách exception đi qua transaction boundary và rollback rules.

Ví dụ, nếu resolver gọi service transactional, service ném InsufficientStockException, Spring rollback transaction rồi exception được chuyển thành GraphQL error bởi cơ chế xử lý lỗi. Khi đó client có thể nhận response:

~~~json
{
  "data": {
    "placeOrder": null
  },
  "errors": [
    {
      "message": "Không đủ tồn kho",
      "path": ["placeOrder"]
    }
  ]
}
~~~

Ngược lại, nếu service bắt exception sau khi đã ghi dữ liệu rồi trả về payload success=false, phương thức kết thúc bình thường nên transaction có thể commit. Nếu payload lỗi phải đồng nghĩa không có thay đổi nào được lưu, cần bảo đảm không ghi trước khi xác định lỗi hoặc chủ động đánh dấu transaction rollback-only.

Một exception được DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler chuyển thành thông báo GraphQL sau khi thoát khỏi service transaction thường không làm thay đổi quyết định rollback đã được transaction interceptor thực hiện. Hãy đặt xử lý exception ở đúng tầng và kiểm thử cả trạng thái database sau lỗi.

## Một mutation operation có nhiều field

GraphQL cho phép một Mutation operation chứa nhiều field cấp cao nhất. Các field đó được chạy tuần tự, nhưng transaction của chúng phụ thuộc cách ứng dụng đặt boundary:

~~~graphql
mutation {
  first: createDraft(input: { title: "GraphQL Basics" }) {
    id
  }
  second: publishBook(id: "book-101") {
    id
  }
}
~~~

Nếu createDraft và publishBook là hai resolver riêng, mỗi resolver gọi một service method có @Transactional, thông thường mỗi lời gọi có transaction riêng. Nếu field đầu tiên commit và field thứ hai thất bại, thay đổi từ field đầu tiên vẫn được giữ.

Khi nghiệp vụ yêu cầu nhiều bước phải nguyên tử, hãy tạo một mutation field duy nhất như createAndPublishBook và một service method duy nhất bao trọn use case. Không dựa vào việc client đặt nhiều field trong cùng operation để tạo một transaction chung.

Nếu thật sự cần transaction bao trùm cả GraphQL execution, đó là một tích hợp cấp execution/transport riêng và cần thiết kế cẩn thận về thời điểm bắt đầu, hoàn tất, xử lý lỗi và các publisher bất đồng bộ. Đây không phải hành vi mặc định của @MutationMapping.

## Propagation và lời gọi service lồng nhau

Spring transaction propagation quyết định một method tham gia transaction hiện tại hay tạo transaction khác. Mặc định Propagation.REQUIRED:

- Nếu chưa có transaction, Spring tạo transaction mới.
- Nếu đã có transaction phù hợp, method tham gia transaction đó.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public OrderService(
            InventoryService inventoryService,
            OrderRepository orderRepository) {
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(PlaceOrderInput input) {
        inventoryService.reserve(input.productId(), input.quantity());
        return orderRepository.save(Order.create(input));
    }
}

@Service
public class InventoryService {

    @Transactional
    public void reserve(String productId, int quantity) {
        // Đọc và cập nhật tồn kho
    }
}
~~~

Nếu InventoryService.reserve được gọi qua bean proxy và dùng propagation mặc định, nó tham gia transaction đang có của OrderService. Nếu bước lưu Order thất bại, cập nhật tồn kho cũng rollback trong cùng transaction.

REQUIRES_NEW tạo transaction độc lập và tạm tách khỏi transaction hiện tại. Nếu dùng nó cho một thao tác phải rollback cùng đơn hàng, dữ liệu của thao tác đó có thể đã commit riêng và không rollback cùng transaction bên ngoài. Chỉ dùng propagation khác mặc định khi hiểu rõ yêu cầu nhất quán.

Transaction annotation dựa trên proxy trong cấu hình Spring phổ biến. Lời gọi một method transactional khác trong cùng một object bằng self-invocation thường không đi qua proxy, vì vậy annotation trên method được gọi nội bộ có thể không tạo boundary mới như mong đợi. Tách nghiệp vụ thành bean service riêng và gọi qua dependency là cách tổ chức dễ hiểu hơn.

## Isolation, khóa dữ liệu và cập nhật đồng thời

Transaction không tự giải quyết mọi vấn đề cạnh tranh dữ liệu. Hai request đặt hàng đồng thời có thể cùng đọc tồn kho là 5 rồi mỗi request đặt 4 sản phẩm. Nếu không có cơ chế bảo vệ, cả hai có thể cùng vượt quá số lượng khả dụng.

Một số kỹ thuật thường dùng:

- **Optimistic locking:** dùng version column và @Version của JPA để phát hiện cập nhật xung đột khi commit.
- **Pessimistic locking:** khóa bản ghi trong lúc transaction xử lý, chẳng hạn truy vấn với lock mode phù hợp.
- **Atomic update:** dùng câu lệnh cập nhật có điều kiện như UPDATE product SET available = available - :qty WHERE id = :id AND available >= :qty, sau đó kiểm tra số hàng được cập nhật.
- **Isolation level:** chọn mức cô lập phù hợp với yêu cầu đọc/ghi và database; mức cao hơn có thể tăng chi phí hoặc contention.

Ví dụ atomic update thường hiệu quả cho tồn kho vì điều kiện kiểm tra và giảm số lượng được thực hiện trong cùng câu lệnh. Tuy nhiên, cần xử lý trường hợp không có bản ghi nào được cập nhật như sản phẩm không tồn tại hoặc không đủ hàng.

Không nên tăng isolation level một cách máy móc để giải quyết mọi lỗi đồng thời. Hãy xác định invariant nghiệp vụ, chọn cơ chế khóa hoặc optimistic concurrency phù hợp và kiểm thử bằng nhiều transaction chạy đồng thời.

## Transaction và tác động bên ngoài

Database transaction thường chỉ bảo đảm tính nguyên tử cho tài nguyên do transaction manager quản lý. Nếu service vừa ghi database vừa gọi HTTP tới payment provider hoặc gửi message tới broker, rollback database không thể tự thu hồi hành động đã hoàn tất ở hệ thống ngoài.

Ví dụ:

1. Ghi đơn hàng vào database.
2. Gọi payment provider để thu tiền thành công.
3. Ghi thông tin thanh toán vào database nhưng bước này thất bại.

Rollback database không hoàn tiền ở payment provider. Với các quy trình phân tán, cần thiết kế cơ chế phù hợp:

- **Transactional outbox:** ghi dữ liệu nghiệp vụ và event vào cùng database transaction; tiến trình riêng đọc outbox và gửi event sau khi commit.
- **Saga:** chia quy trình thành nhiều transaction cục bộ, mỗi bước có hành động bù trừ khi bước sau thất bại.
- **Idempotency:** dùng request key duy nhất để request lặp lại không tạo đơn hoặc thu tiền nhiều lần.
- **Retry có kiểm soát:** chỉ retry thao tác có thể lặp an toàn và có giới hạn.

Không giữ database transaction mở trong thời gian dài để chờ một HTTP call chậm nếu có thể tách quy trình. Transaction dài làm tăng thời gian giữ lock và có thể giảm thông lượng.

## Reactive transaction với Spring WebFlux

Nếu ứng dụng sử dụng WebFlux và các repository reactive như R2DBC, service có thể trả về Mono hoặc Flux. Spring hỗ trợ reactive transaction thông qua ReactiveTransactionManager. Khi dùng @Transactional cho một phương thức trả về reactive publisher, transaction được gắn với quá trình subscribe và Reactor context, không dựa vào thread-local như transaction imperative.

Ví dụ service reactive:

~~~java
@Service
public class ReactiveOrderService {

    private final ReactiveProductRepository products;
    private final ReactiveOrderRepository orders;

    public ReactiveOrderService(
            ReactiveProductRepository products,
            ReactiveOrderRepository orders) {
        this.products = products;
        this.orders = orders;
    }

    @Transactional
    public Mono<OrderReceipt> placeOrder(PlaceOrderInput input) {
        return products.findById(input.productId())
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(input.productId())))
                .flatMap(product -> {
                    if (input.quantity() <= 0
                            || product.getAvailableQuantity() < input.quantity()) {
                        return Mono.error(
                                new InsufficientStockException(product.getId()));
                    }

                    product.decreaseAvailableQuantity(input.quantity());
                    return products.save(product)
                            .then(orders.save(Order.create(input, product)))
                            .map(OrderReceipt::from);
                });
    }
}
~~~

Để transaction hoạt động reactive, ứng dụng cần cấu hình reactive transaction manager phù hợp với nguồn dữ liệu, ví dụ R2DBC. Các thao tác cần nằm trong cùng reactive pipeline và lỗi phải được truyền tiếp để transaction có thể rollback.

Không gọi block() bên trong pipeline hoặc chuyển một phần công việc sang luồng không mang Reactor context nếu vẫn kỳ vọng nó tham gia cùng reactive transaction. Cũng không nên dùng imperative transaction manager cho một quy trình reactive rồi cho rằng transaction sẽ tự theo publisher. Nếu dùng JDBC/JPA blocking, hãy chọn mô hình imperative phù hợp hoặc cô lập rõ phần blocking; đừng trộn hai mô hình transaction mà không có thiết kế cụ thể.

## Kiểm thử mutation transaction

Một bài kiểm thử transaction nên xác minh cả GraphQL response lẫn trạng thái lưu trữ sau khi mutation kết thúc. Có thể dùng GraphQlTester để gọi operation:

~~~java
graphQlTester.document("""
        mutation PlaceOrder($input: PlaceOrderInput!) {
            placeOrder(input: $input) {
                orderId
                status
            }
        }
        """)
    .variable("input", Map.of(
            "productId", "p-10",
            "quantity", 2,
            "requestId", "req-2025-0001"))
    .execute()
    .path("placeOrder.status")
    .entity(String.class)
    .isEqualTo("CREATED");
~~~

Ngoài trường hợp thành công, nên kiểm tra:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Sản phẩm không tồn tại | Không có đơn hàng hoặc thay đổi tồn kho |
| Không đủ tồn kho | Tồn kho không bị giảm và đơn hàng không được tạo |
| Lưu đơn hàng phát sinh lỗi sau khi giảm tồn kho | Thay đổi tồn kho được rollback |
| Checked exception với rollbackFor | Transaction rollback theo cấu hình |
| Client gửi lại cùng requestId | Không tạo tác động nghiệp vụ trùng lặp nếu API hỗ trợ idempotency |
| Hai request đặt hàng đồng thời | Invariant tồn kho vẫn được bảo toàn |
| Mutation gọi hệ thống ngoài | Xác minh outbox, retry hoặc hành động bù trừ theo thiết kế |

Để kiểm tra rollback thật, test cần quan sát database sau khi transaction của service đã kết thúc. Cẩn thận với test method được gắn @Transactional: transaction bao quanh test có thể khiến dữ liệu test rollback khi kết thúc test, che khuất việc transaction bên trong mutation đã commit hay rollback như thế nào. Với các kịch bản này, có thể dùng transaction test được kiểm soát rõ ràng hoặc kiểm tra từ một transaction độc lập sau khi request hoàn tất.

## Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mutation báo lỗi nhưng dữ liệu vẫn thay đổi | Exception bị bắt và chuyển thành payload bình thường trong transaction | Không nuốt exception nếu cần rollback; đánh dấu rollback-only khi phù hợp |
| Bước đầu commit, bước sau thất bại | Mỗi resolver/service có transaction riêng | Gom các thao tác thành một use case và một transaction |
| @Transactional không có tác dụng | Method được gọi nội bộ qua self-invocation hoặc bean không qua proxy | Gọi qua Spring bean proxy và dùng method phù hợp |
| Checked exception không rollback | Quy tắc mặc định chỉ rollback RuntimeException và Error | Khai báo rollbackFor khi cần |
| Tồn kho âm khi nhiều request đồng thời | Thiếu khóa hoặc cập nhật nguyên tử | Dùng optimistic/pessimistic locking hoặc atomic update |
| Gửi email/message rồi database rollback | Hệ thống ngoài không thuộc local transaction | Dùng outbox, saga hoặc hành động bù trừ |
| Reactive transaction không rollback như mong đợi | Dùng sai transaction manager hoặc làm đứt reactive pipeline | Dùng ReactiveTransactionManager và giữ lỗi trong publisher |
| Lazy field lỗi sau mutation | Transaction kết thúc trước khi GraphQL phân giải field con | Trả DTO/projection có dữ liệu cần thiết hoặc thiết kế fetch rõ ràng |

## Nguyên tắc thiết kế mutation transaction

Khi xây dựng mutation trong Spring for GraphQL, hãy áp dụng những nguyên tắc sau:

1. **Thiết kế mutation theo use case.** Một field nên đại diện cho một hành động nghiệp vụ hoàn chỉnh.
2. **Đặt transaction ở service.** Gom các thao tác dữ liệu phải cùng thành công hoặc thất bại vào một method có @Transactional.
3. **Hiểu rollback rule.** Phân biệt RuntimeException, checked exception và trường hợp exception bị bắt.
4. **Không nhầm thứ tự GraphQL với transaction.** Mutation root fields chạy tuần tự nhưng không tự chia sẻ một transaction chung.
5. **Kiểm soát đồng thời.** Bảo vệ invariant bằng locking, version hoặc atomic update.
6. **Tách side effect phân tán.** Dùng outbox hoặc saga khi cần phối hợp database với hệ thống ngoài.
7. **Giữ reactive transaction nhất quán.** Dùng đúng transaction manager và không chặn pipeline.
8. **Trả DTO phù hợp.** Đừng phụ thuộc vào lazy entity sau khi transaction kết thúc.
9. **Kiểm thử trạng thái database.** Xác minh cả commit và rollback, không chỉ kiểm tra GraphQL response.

Mutation transaction là ranh giới bảo đảm tính nguyên tử cho một use case thay đổi dữ liệu. Spring for GraphQL ánh xạ mutation field vào resolver; service method với @Transactional điều phối transaction; transaction manager quyết định commit hoặc rollback theo kết quả thực thi. Khi thiết kế mutation theo nghiệp vụ, kiểm soát lỗi và đồng thời, đồng thời tách side effect ngoài database bằng outbox hoặc saga, API sẽ giữ được trạng thái dữ liệu nhất quán ngay cả khi một bước xử lý thất bại.
