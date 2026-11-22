# Thiết kế schema theo domain

GraphQL schema là contract mà client sử dụng để đọc và thay đổi dữ liệu. Khi thiết kế schema theo domain, type, field, input và mutation cần diễn đạt khái niệm nghiệp vụ mà hệ thống hỗ trợ, thay vì phản chiếu trực tiếp bảng database hoặc entity JPA.

Trong Spring for GraphQL, schema SDL định nghĩa contract; resolver ánh xạ field sang application service; service thực thi use case và gọi domain logic hoặc repository. Cách tổ chức này giúp API giữ được ngôn ngữ của nghiệp vụ ngay cả khi database, ORM hoặc cách triển khai service thay đổi.

Ví dụ, một hệ thống bán hàng có thể có các domain Catalog, Ordering và Customer. Catalog quản lý thông tin sản phẩm; Ordering quản lý giỏ hàng, đơn hàng và trạng thái đặt hàng; Customer quản lý hồ sơ khách hàng. GraphQL schema có thể kết hợp các khái niệm đó thành một graph dễ dùng, nhưng mỗi field vẫn cần có owner và semantics rõ ràng.

## 1. Schema là contract của domain và client

GraphQL schema trả lời ba câu hỏi:

1. Client có thể yêu cầu những khái niệm nghiệp vụ nào?
2. Client có thể thực hiện những hành động nào?
3. Dữ liệu và lỗi được biểu diễn theo quy tắc nào?

Schema không phải bản sao của database. Một bảng product có thể có hàng chục cột kỹ thuật như internal_status, created_by, row_version, deleted_at hoặc supplier_cost. Client chỉ nên nhìn thấy những field có ý nghĩa với use case và được phép truy cập.

Tương tự, một domain aggregate có thể gồm nhiều entity nội bộ nhưng API chỉ cần trả một read model phù hợp với màn hình. Ngược lại, một GraphQL type có thể tổng hợp dữ liệu từ nhiều aggregate hoặc service nếu đó là một khái niệm hợp lý đối với client.

| Thành phần | Nên phản ánh | Tránh phản ánh trực tiếp |
| --- | --- | --- |
| GraphQL type | Khái niệm nghiệp vụ hoặc read model | Tên bảng/entity ORM |
| Field | Thuộc tính hoặc quan hệ có ý nghĩa với client | Mọi cột database |
| Query | Nhu cầu đọc/use case | Repository method hoặc SQL |
| Mutation | Hành động nghiệp vụ | Generic insert/update/delete |
| Input type | Dữ liệu cần để thực hiện hành động | Entity JPA có thể ghi trực tiếp |
| Error | Kết quả hoặc lỗi theo contract | Stack trace và exception nội bộ |

Một schema tốt giúp client hiểu domain mà không phải biết hệ thống lưu dữ liệu ở đâu hoặc service nào đang xử lý.

## 2. Bắt đầu từ bounded context

Trong Domain-Driven Design, bounded context là ranh giới mà trong đó một mô hình domain và ngôn ngữ nghiệp vụ có ý nghĩa nhất quán. Một từ có thể mang ý nghĩa khác nhau giữa các context.

Ví dụ từ Product:

- Trong Catalog, Product là mặt hàng đang được bán, có tên, mô tả, giá hiện tại và trạng thái hiển thị.
- Trong Ordering, một dòng đơn hàng cần lưu tên và đơn giá tại thời điểm đặt hàng để hóa đơn không thay đổi khi Catalog cập nhật sản phẩm.
- Trong Shipping, Product có thể chỉ cần kích thước, trọng lượng và yêu cầu đóng gói.

Không nên ép tất cả các context dùng chung một object Product với mọi field. Nếu semantics khác nhau, hãy biểu diễn rõ bằng type phù hợp, ví dụ Product, OrderLineProductSnapshot và ShippableItem.

Schema GraphQL có thể thống nhất trải nghiệm truy vấn, nhưng không làm mất đi sự khác biệt của bounded context. Việc dùng chung một tên type chỉ hợp lý khi các service thực sự chia sẻ cùng semantics và ownership được định nghĩa rõ.

## 3. Dùng ubiquitous language trong type và field

Ubiquitous language là ngôn ngữ chung giữa người làm nghiệp vụ và đội phát triển trong một bounded context. Tên type, field, enum và mutation nên dùng từ mà domain team hiểu và sử dụng.

| Tên kỹ thuật hoặc mơ hồ | Tên theo domain rõ hơn |
| --- | --- |
| statusCode | fulfillmentStatus hoặc paymentStatus |
| process | placeOrder hoặc cancelOrder |
| data | orderSummary hoặc productDetails |
| userRef | customer |
| amount | total, unitPrice hoặc refundAmount |
| updateRecord | changeShippingAddress |

Tránh dùng một field status cho nhiều khái niệm. Đơn hàng có thể có orderStatus, paymentStatus và fulfillmentStatus; chúng thay đổi theo các quy tắc khác nhau.

Tên field cũng nên mô tả semantics ổn định. Nếu field price là giá hiện tại của Catalog, ghi rõ đơn vị tiền và cách tính. Nếu field total là tổng tiền đơn hàng, định nghĩa rõ có bao gồm thuế, phí vận chuyển và giảm giá hay không.

## 4. Phân biệt domain model, persistence model và GraphQL model

Ba mô hình này có thể liên quan nhưng không cần giống nhau:

| Mô hình | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Domain model | Bảo vệ invariant và quy tắc nghiệp vụ | Order aggregate, OrderLine, Money |
| Persistence model | Lưu và truy vấn dữ liệu | JPA entity, relation, index, join table |
| GraphQL model | Cung cấp contract cho client | Order, OrderItem, OrderConnection |

Ví dụ JPA entity:

~~~java
@Entity
public class OrderEntity {

    @Id
    private UUID id;

    private UUID customerId;
    private String internalState;
    private BigDecimal totalAmount;
    private String currencyCode;
    private long version;
    private Instant createdAt;

    // JPA relationships and persistence details
}
~~~

GraphQL có thể công bố:

~~~graphql
type Order {
    id: ID!
    status: OrderStatus!
    total: Money!
    placedAt: DateTime!
    items: [OrderItem!]!
}
~~~

GraphQL type không cần lộ internalState, version hoặc các cột kỹ thuật. Resolver/service chuyển đổi từ domain hoặc read model sang GraphQL response type.

Nếu trả trực tiếp JPA entity, thay đổi mapping database có thể vô tình làm thay đổi API, getter có thể kích hoạt lazy loading và field mặc định có thể làm lộ dữ liệu không nên công bố. DTO/read model giúp kiểm soát contract tốt hơn.

## 5. Thiết kế schema từ use case

Hãy bắt đầu bằng những câu hỏi client cần trả lời, sau đó xác định domain service nào sở hữu dữ liệu:

- Trang danh mục cần tìm và lọc sản phẩm.
- Trang chi tiết cần thông tin sản phẩm, giá và tình trạng còn hàng.
- Trang đơn hàng cần trạng thái, tổng tiền và các dòng hàng.
- Người mua cần đặt hàng, hủy đơn hoặc thay đổi địa chỉ giao hàng theo điều kiện nghiệp vụ.

Từ đó tạo root query:

~~~graphql
type Query {
    product(id: ID!): Product
    searchProducts(input: ProductSearchInput!): ProductConnection!
    order(id: ID!): Order
    myOrders(first: Int = 20, after: String): OrderConnection!
}
~~~

Query name diễn đạt nhu cầu đọc theo ngôn ngữ domain. Không cần expose findProductById, selectOrders hoặc getProductFromDatabase. Cách đặt tên có thể theo convention của dự án, nhưng semantics phải rõ.

Một query có thể trả read model tổng hợp từ nhiều nguồn. Ví dụ orderDetails có thể gồm thông tin đơn hàng, trạng thái thanh toán và thông tin vận chuyển. Tuy nhiên, cần cân nhắc latency, quyền sở hữu field và khả năng một dependency bị lỗi.

## 6. Thiết kế GraphQL type theo khái niệm nghiệp vụ

Ví dụ schema cho Catalog và Ordering:

~~~graphql
scalar DateTime
scalar Decimal

type Product {
    id: ID!
    name: String!
    description: String
    price: Money!
    availability: ProductAvailability!
}

type Money {
    amount: Decimal!
    currency: CurrencyCode!
}

type Order {
    id: ID!
    status: OrderStatus!
    placedAt: DateTime!
    total: Money!
    items: [OrderItem!]!
}

type OrderItem {
    quantity: Int!
    unitPrice: Money!
    product: OrderLineProductSnapshot!
}

type OrderLineProductSnapshot {
    productId: ID!
    nameAtPurchase: String!
}

enum ProductAvailability {
    IN_STOCK
    OUT_OF_STOCK
    PREORDER
}

enum OrderStatus {
    PENDING
    CONFIRMED
    CANCELLED
    FULFILLED
}
enum CurrencyCode {
    VND
    USD
    EUR
}
~~~

Schema trên phân biệt Product hiện tại của Catalog với snapshot tên sản phẩm tại thời điểm mua. OrderLineProductSnapshot giúp lịch sử đơn hàng không bị thay đổi khi Product.name được cập nhật.

Money là value object có amount và currency thay vì chỉ trả BigDecimal không có đơn vị. Decimal và CurrencyCode cần được định nghĩa bằng scalar hoặc enum phù hợp với contract; không dùng Float cho phép tính tiền yêu cầu độ chính xác thập phân.

DateTime và Decimal là custom scalar trong ví dụ. Khai báo scalar trong SDL chưa đủ để xử lý dữ liệu; ứng dụng cần đăng ký GraphQLScalarType/Coercing tương ứng qua RuntimeWiringConfigurer hoặc cơ chế wiring phù hợp. CurrencyCode là enum nên GraphQL Java có thể xử lý như enum sau khi type được khai báo.

## 7. Chọn type và field theo ngữ nghĩa

Các lựa chọn type ảnh hưởng trực tiếp đến contract:

- Dùng ID cho identifier mà client truyền lại, không bắt buộc ID phải là UUID.
- Dùng enum cho tập giá trị hữu hạn và có ý nghĩa nghiệp vụ.
- Dùng object type cho value object gồm nhiều thành phần.
- Dùng input object cho tập dữ liệu đầu vào của query/mutation.
- Dùng connection cho collection lớn cần phân trang.
- Dùng custom scalar khi có format và quy tắc serialize/parse rõ ràng.

Không dùng String cho mọi thứ. Một field ngày giờ, tiền tệ, trạng thái hoặc địa chỉ có thể cần type rõ hơn để giảm nhập nhằng.

Custom scalar cần có coercing logic, format và validation thống nhất giữa server và client. Ví dụ DateTime nên công bố timezone/offset và định dạng ISO-8601 mà API chấp nhận. Không tạo scalar chỉ để đổi tên String nếu không có semantics hoặc validation bổ sung.

## 8. Input type và output type nên tách biệt

Input phục vụ hành động và output mô tả trạng thái hoặc kết quả. Không tái sử dụng một type cho cả hai chiều chỉ vì các field trùng nhau.

Ví dụ input đặt hàng:

~~~graphql
input PlaceOrderInput {
    items: [PlaceOrderItemInput!]!
    shippingAddress: ShippingAddressInput!
    idempotencyKey: String!
}

input PlaceOrderItemInput {
    productId: ID!
    quantity: Int!
}

input ShippingAddressInput {
    recipientName: String!
    addressLine1: String!
    city: String!
    postalCode: String
    countryCode: String!
}
~~~

Input chỉ nhận những giá trị caller được phép cung cấp. Không cho client gửi total, orderStatus, createdAt, tenantId hoặc internalVersion nếu các giá trị đó do server/domain quyết định.

Output:

~~~graphql
type PlaceOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: String
}
~~~

Tách input/output giúp API thay đổi độc lập. Ví dụ server có thể thêm field computed vào Order mà không biến nó thành field client được phép ghi.

## 9. Mutation nên biểu diễn hành động nghiệp vụ

Mutation nên mô tả command hoặc use case, không chỉ là generic CRUD:

~~~graphql
type Mutation {
    placeOrder(input: PlaceOrderInput!): PlaceOrderPayload!
}
~~~

Một mutation placeOrder có thể cần kiểm tra:

1. Product còn được bán hay không.
2. Số lượng có hợp lệ không.
3. Giá và khuyến mãi hiện tại.
4. Quyền đặt hàng của customer.
5. Địa chỉ giao hàng có được hỗ trợ không.
6. Các invariant của Order aggregate.

Nếu schema chỉ có updateOrder(id, fields), client có thể gửi trạng thái tùy ý hoặc tạo chuyển trạng thái không hợp lệ. Mutation theo hành động giúp domain kiểm soát transition và validation.

Mutation resolver nên gọi application service/command handler. Không viết toàn bộ quy tắc đặt hàng trong controller hoặc resolver.

## 10. Đặt tên và tổ chức root fields

Query root là điểm vào của các use case đọc. Mutation root là điểm vào của các command. Subscription root là điểm vào của event stream nếu domain có nhu cầu realtime.

Ví dụ mở rộng root query:

~~~graphql
extend type Query {
    productsByCategory(categoryId: ID!, first: Int = 20): ProductConnection!
}
~~~

Root Query và Mutation đã được khai báo ở các phần trước; khi tách SDL theo file, dùng extend type để thêm field vào root type hiện có. Tránh tạo một root field quá tổng quát như entity(type, id) hoặc execute(command, payload). Những field này làm client mất type safety và đẩy semantics vào JSON/string không có schema rõ ràng.

Không cần tạo root field cho mọi repository method. API chỉ nên công bố những operation có giá trị với client.

## 11. Quan hệ giữa type và aggregate boundary

Aggregate là ranh giới nhất quán nghiệp vụ. Một aggregate root kiểm soát các invariant của những object nằm bên trong aggregate.

GraphQL object graph có thể rộng hơn aggregate graph. Ví dụ Order có customer và product; nhưng Customer, Product và Order có thể thuộc các aggregate hoặc bounded context khác nhau.

Khi resolve một field quan hệ:

- Nếu dữ liệu nằm trong cùng aggregate và cần cho use case, application service có thể tải cùng aggregate.
- Nếu dữ liệu thuộc aggregate khác trong cùng service, cân nhắc query service hoặc DataLoader.
- Nếu dữ liệu thuộc service khác, gọi contract của service owner hoặc dùng Federation.
- Nếu field cần dữ liệu lịch sử, lưu snapshot/value object thay vì truy vấn giá trị hiện tại.

Không tạo quan hệ JPA trực tiếp xuyên service. GraphQL có thể biểu diễn quan hệ bằng ID và resolver, nhưng persistence boundary vẫn phải được giữ.

## 12. Không biến GraphQL type thành object graph vô hạn

Một schema có thể tạo vòng quan hệ:

~~~graphql
type Customer {
    orders: [Order!]!
}

type Order {
    customer: Customer!
}
~~~

Vòng tham chiếu type hợp lệ trong GraphQL. Tuy nhiên, query có thể lặp sâu:

~~~graphql
query {
    customer(id: "c-1") {
        orders {
            customer {
                orders {
                    customer {
                        id
                    }
                }
            }
        }
    }
}
~~~

Không phải mọi quan hệ trong domain đều cần được expose hai chiều. Có thể chỉ cung cấp Customer.orders và Order.customerSummary nếu use case cần. Với collection lớn, dùng connection và giới hạn page size.

Depth limit, complexity limit và DataLoader giúp kiểm soát chi phí, nhưng thiết kế schema có hướng đi rõ vẫn quan trọng hơn việc expose mọi quan hệ rồi tìm cách giới hạn sau.

## 13. Field ownership và resolver boundary

Mỗi field nên có nguồn dữ liệu và owner rõ ràng. Ví dụ:

| Field | Owner | Resolver/use case |
| --- | --- | --- |
| Product.name | Catalog | ProductQueryService |
| Product.price | Pricing/Catalog theo mô hình domain | PriceQueryService |
| Order.status | Ordering | OrderQueryService |
| Order.total | Ordering | Order total/read model |
| Order.customer | Customer hoặc Order read model | CustomerClient/DataLoader |
| OrderItem.nameAtPurchase | Ordering | Snapshot trong Order |

Trong monolith modular, owner có thể là module ứng dụng. Trong microservices, owner thường là service sở hữu dữ liệu. Resolver có thể gọi owner service thông qua API client hoặc DataLoader.

Không để field phụ thuộc ngầm vào getter của JPA entity nếu điều đó làm query phát sinh không kiểm soát. Resolver tường minh giúp thấy field đang gọi service nào và có thể instrument/test riêng.

## 14. Triển khai resolver mỏng trong Spring for GraphQL

SDL định nghĩa field; @QueryMapping, @MutationMapping và @SchemaMapping ánh xạ field tới method Java.

~~~java
@Controller
public class ProductQueryController {

    private final ProductQueryService productQueryService;

    public ProductQueryController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @QueryMapping
    public Product product(@Argument String id, Principal principal) {
        return productQueryService.findVisibleProduct(id, principal);
    }

    @QueryMapping
    public ProductConnection searchProducts(
            @Argument ProductSearchInput input,
            Principal principal) {
        return productQueryService.search(input, principal);
    }
}
~~~

Controller chịu trách nhiệm binding và điều phối. ProductQueryService xử lý filter, authorization, repository/client và mapping sang GraphQL read model.

Với mutation:

~~~java
@Controller
public class OrderMutationController {

    private final PlaceOrderUseCase placeOrderUseCase;

    public OrderMutationController(PlaceOrderUseCase placeOrderUseCase) {
        this.placeOrderUseCase = placeOrderUseCase;
    }

    @MutationMapping
    public PlaceOrderPayload placeOrder(
            @Argument PlaceOrderInput input,
            Principal principal) {
        return placeOrderUseCase.execute(input, principal);
    }
}
~~~

Resolver không nên tự mở transaction, thay đổi nhiều entity hoặc gọi repository trực tiếp nếu use case có quy tắc nghiệp vụ. Application service sở hữu transaction boundary và gọi domain model.

## 15. Dùng @SchemaMapping cho quan hệ có ý nghĩa

Một field không nhất thiết cần resolver riêng nếu Spring GraphQL có thể đọc property từ source object. Nhưng khi field cần gọi service, áp dụng policy hoặc chuyển đổi dữ liệu, @SchemaMapping giúp thể hiện rõ:

~~~java
@Controller
public class OrderFieldController {

    private final CustomerQueryService customerQueryService;

    public OrderFieldController(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @SchemaMapping(typeName = "Order", field = "customer")
    public CustomerSummary customer(Order order, Principal principal) {
        return customerQueryService.findVisibleSummary(
            order.customerId(), principal);
    }
}
~~~

Nếu nhiều Order cùng cần Customer, resolver trên có thể tạo N+1. Dùng @BatchMapping hoặc DataLoader để gom customer ID thành một batch. Batch loader phải áp dụng cùng authorization scope và không chia sẻ cache giữa các principal.

## 16. Domain schema và read model

GraphQL thường phục vụ truy vấn linh hoạt, vì vậy response model không nhất thiết là domain aggregate nguyên bản. Có thể xây read model riêng để trả dữ liệu đã tổng hợp:

~~~java
public record OrderSummary(
        String id,
        OrderStatus status,
        Money total,
        Instant placedAt,
        int itemCount) {
}
~~~

Read model có thể lấy từ projection, query service hoặc CQRS read store. Nó giúp tối ưu các màn hình mà không buộc domain aggregate phải có đúng cấu trúc GraphQL cần.

Tuy nhiên, không tạo một read model mới cho mọi selection set nhỏ. Chọn abstraction dựa trên use case, chi phí query và khả năng tái sử dụng. Với field quan hệ được yêu cầu độc lập, DataLoader có thể phù hợp hơn.

## 17. Thiết kế nullability theo invariant

Dấu ! trong GraphQL SDL có ý nghĩa contract:

- String! nghĩa field luôn có giá trị khi parent được trả.
- String nghĩa field có thể null.
- [Order!]! nghĩa list luôn tồn tại và từng phần tử không null.
- [Order] cho phép cả list và từng phần tử có thể null.

Chỉ khai báo non-null khi domain hoặc read model bảo đảm invariant đó. Ví dụ Order.id thường non-null. Customer của Order có thể không còn hiển thị do privacy policy hoặc dữ liệu legacy; nếu API có thể trả null, không nên khai báo Customer! chỉ vì quan hệ database từng là bắt buộc.

Nullability cũng ảnh hưởng khi resolver lỗi. Nếu field non-null lỗi, GraphQL null propagation có thể làm parent trở thành null và lan lên cao hơn. Với field phụ thuộc service bên ngoài, cần cân nhắc partial failure và contract client.

Không dùng non-null như cách ép dữ liệu phải có. Hãy bảo đảm dữ liệu và resolver thực sự đáp ứng contract.

## 18. Thiết kế collection và pagination

Không trả collection không giới hạn cho domain có thể tăng dữ liệu theo thời gian. Ví dụ myOrders nên có first/after và connection:

~~~graphql
input ProductSearchInput {
    keyword: String
    availability: ProductAvailability
}

type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
}

type ProductEdge {
    cursor: String!
    node: Product!
}

type OrderConnection {
    edges: [OrderEdge!]!
    pageInfo: PageInfo!
}

type OrderEdge {
    cursor: String!
    node: Order!
}

type PageInfo {
    hasNextPage: Boolean!
    hasPreviousPage: Boolean!
    startCursor: String
    endCursor: String
}
~~~

Pagination cần sort order ổn định, cursor gắn với sort key và filter, page size cap và authorization scope. Với dữ liệu lớn, keyset/cursor pagination thường phù hợp hơn offset ở các trang sâu.

totalCount chỉ nên cung cấp khi client thực sự cần và database có thể tính với chi phí chấp nhận được. Không chạy COUNT(*) chỉ để xác định có trang tiếp theo; query n + 1 thường đủ.

## 19. Error contract theo domain

Lỗi nghiệp vụ và lỗi thực thi GraphQL cần được phân biệt:

- Product không tồn tại: NOT_FOUND hoặc null theo contract query.
- Không có quyền xem Order: FORBIDDEN hoặc cách ẩn sự tồn tại theo policy.
- Số lượng đặt hàng không hợp lệ: validation error.
- Hết hàng: có thể là business outcome của placeOrder, không nhất thiết là lỗi hệ thống.
- Database timeout: lỗi nội bộ/dependency, không phải BAD_REQUEST.

Với mutation, có thể biểu diễn kết quả nghiệp vụ trong payload:

~~~graphql
type PlaceOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: String
}
~~~

Ví dụ OUT_OF_STOCK có thể là userError nếu client cần hiển thị nguyên nhân và cho phép thay đổi giỏ hàng. Exception không dự kiến vẫn nên đi qua GraphQL error handling với message an toàn, error code ổn định và log nội bộ.

Đừng dùng payload errors để che mọi lỗi. Phân biệt lỗi người dùng có thể sửa, business state hợp lệ nhưng không thành công, và lỗi hạ tầng khiến operation không thể hoàn tất.

## 20. Authorization theo domain và field

Schema công khai một field không có nghĩa mọi user đều được đọc field đó. Authorization cần kiểm tra ở service hoặc resolver theo principal, tenant, resource và action.

~~~java
@SchemaMapping(typeName = "Order", field = "internalNotes")
public String internalNotes(Order order, Principal principal) {
    orderAccessService.checkCanReadInternalNotes(principal, order.id());
    return order.internalNotes();
}
~~~

Ví dụ minh họa kiểm tra policy trước khi trả field; cách triển khai thực tế có thể dùng method security, authorization service hoặc reactive result tùy stack.

Không dựa vào việc client không query field để bảo vệ dữ liệu. Không đưa internal field vào schema nếu client không cần. Với field nhạy cảm, dùng field-level authorization và test cả truy cập trực tiếp lẫn qua nested resolver.

Nếu dữ liệu phụ thuộc tenant, mọi repository query, downstream call và DataLoader batch đều phải áp dụng tenant scope. Không nhận tenant ID từ input nếu server có thể xác định từ security context.

## 21. Tổ chức SDL theo domain module

Khi schema lớn, tách SDL theo capability hoặc bounded context giúp ownership rõ hơn:

~~~text
src/main/resources/graphql/
  common/
    scalars.graphqls
    pagination.graphqls
  catalog/
    product.graphqls
    product-search.graphqls
  ordering/
    order.graphqls
    place-order.graphqls
  customer/
    customer.graphqls
~~~

Một file có thể khai báo root type; file khác mở rộng bằng extend:

~~~graphql
type Query {
    product(id: ID!): Product
}
~~~

~~~graphql
extend type Query {
    order(id: ID!): Order
    myOrders(first: Int = 20, after: String): OrderConnection!
}
~~~

Spring Boot có thể tải nhiều SDL resource theo cấu hình schema locations. Ví dụ:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Giữ file SDL ở đúng vị trí cấu hình và kiểm tra schema được merge thành công khi ứng dụng khởi động. Không khai báo trùng field hoặc định nghĩa type mâu thuẫn giữa các file.

## 22. Modular hóa resolver và application service

Tổ chức package theo domain/capability thay vì gom mọi resolver vào một class lớn:

~~~text
com.example.shop/
  catalog/
    api/
      ProductQueryController.java
      ProductFieldController.java
      ProductSearchInput.java
    application/
      ProductQueryService.java
    domain/
      Product.java
      Money.java
    infrastructure/
      ProductRepository.java
  ordering/
    api/
      OrderQueryController.java
      OrderMutationController.java
      OrderFieldController.java
    application/
      PlaceOrderUseCase.java
      OrderQueryService.java
    domain/
      Order.java
      OrderLine.java
    infrastructure/
      OrderRepository.java
~~~

Package layout chỉ là một ví dụ. Điều quan trọng là resolver thuộc API layer, application service điều phối use case, domain giữ invariant và infrastructure triển khai persistence/client.

Không để SDL file structure trở thành ranh giới domain duy nhất. Ownership phải được thể hiện trong code, module dependency và quy trình review.

## 23. Tiến hóa schema mà không phá client

GraphQL schema là contract có thể được nhiều client sử dụng cùng lúc. Thay đổi nên ưu tiên additive:

- Thêm field mới thường ít rủi ro hơn đổi field hiện có.
- Thêm argument bắt buộc vào field đang dùng có thể phá client cũ.
- Đổi kiểu scalar hoặc enum có thể phá code generation và client validation.
- Đổi nullability từ nullable sang non-null là thay đổi breaking.
- Xóa field hoặc enum value đang được dùng là breaking.
- Đổi semantics mà giữ nguyên tên cũng là breaking về hành vi.

Khi cần thay field:

1. Thêm field mới với semantics rõ.
2. Giữ field cũ trong giai đoạn chuyển đổi.
3. Đánh dấu field cũ bằng @deprecated(reason: "...").
4. Theo dõi usage nếu có instrumentation.
5. Thông báo client và chờ adoption.
6. Chỉ xóa khi đã xác nhận không còn consumer cần field cũ.

Ví dụ:

~~~graphql
type Product {
    price: Float @deprecated(reason: "Use priceDetails for currency-aware pricing")
    priceDetails: Money!
}
~~~

Đây là ví dụ migration độc lập từ một schema cũ có price kiểu Float; nó minh họa cách giữ field cũ trong thời gian chuyển đổi và bổ sung field mới có currency.

Không thêm argument bắt buộc khi muốn mở rộng query; dùng default phù hợp hoặc tạo field/use case mới. Khi thêm enum value, lưu ý một số client dùng exhaustive switch có thể không xử lý giá trị mới.

## 24. Tránh over-fetching và under-fetching trong thiết kế

GraphQL cho phép client chọn field nên có thể giảm over-fetching ở response. Tuy nhiên, schema quá tổng quát hoặc resolver không có fetch plan có thể khiến server over-fetch dữ liệu.

Ví dụ client chỉ cần Product.name nhưng resolver luôn tải toàn bộ reviews, inventory history và supplier details thì server vẫn over-fetch.

Ngược lại, nếu client cần ghép nhiều query riêng cho một màn hình vì schema không có field tổng hợp phù hợp, API có thể under-serve use case. Hãy thiết kế query/read model theo nhu cầu thực tế mà không biến schema thành endpoint riêng cho từng pixel UI.

Có thể dùng projection, DataLoader, @BatchMapping, selection set inspection hoặc query service chuyên biệt để kiểm soát dữ liệu được tải. Chỉ dùng selection set để tối ưu khi mapping field-to-column rõ ràng và có test; tránh biến resolver thành một query planner tùy biến khó bảo trì.

## 25. Kiểm thử schema theo domain

GraphQlTester có thể kiểm tra SDL, resolver, nullability và error contract:

~~~java
@SpringBootTest
class ProductGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    private GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }

    @Test
    void exposesProductFieldsInDomainLanguage() {
        var response = graphQlTester.document("""
                query {
                    product(id: "p-100") {
                        id
                        name
                        price {
                            amount
                            currency
                        }
                    }
                }
                """)
            .execute();

        response.errors().verify();
        response.path("product.name")
            .entity(String.class)
            .isEqualTo("Mechanical Keyboard");
        response.path("product.price.currency")
            .entity(String.class)
            .isEqualTo("VND");
    }
}
~~~

Ngoài response test, cần kiểm tra:

- Field và type được đặt tên theo ubiquitous language.
- Client không thể ghi field do server quản lý.
- Nullability đúng với domain invariant và partial failure.
- Mutation gọi đúng use case và không bypass aggregate rules.
- Authorization áp dụng cho root và nested fields.
- Pagination giữ sort order ổn định và có page size cap.
- DataLoader không tạo N+1.
- Field deprecated vẫn hoạt động trong thời gian chuyển đổi.
- Schema thay đổi không phá client contract.

Có thể thêm schema diff hoặc contract check trong CI để phát hiện breaking change trước khi deploy.

## 26. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| GraphQL type phản chiếu entity JPA | API bị ràng buộc vào persistence và dễ lộ field | Dùng GraphQL DTO/read model |
| Một Product type dùng cho mọi bounded context | Trộn semantics và ownership | Tách snapshot/reference type khi ý nghĩa khác |
| Mutation generic updateEntity | Bypass domain command và invariant | Mutation theo hành động nghiệp vụ |
| Input tái sử dụng output type | Client có thể gửi field server quản lý | Tách input và output |
| Field status quá chung | Client không hiểu trạng thái thuộc quy trình nào | Dùng orderStatus, paymentStatus, fulfillmentStatus |
| Expose mọi quan hệ hai chiều | Query sâu và graph khó kiểm soát | Chỉ expose relationship có use case |
| Collection không phân trang | Response và query tăng không giới hạn | Connection, cursor và page size cap |
| Non-null cho field phụ thuộc không ổn định | Một lỗi nhỏ làm null cả parent graph | Thiết kế nullability theo invariant |
| Resolver gọi repository trực tiếp ở mọi field | Business logic và transaction rải rác | Dùng application service/query service |
| Resolver gọi service theo từng parent | Network N+1 | Batch API và DataLoader |
| Lộ internal field rồi chỉ ẩn ở UI | Dữ liệu vẫn truy cập được qua API | Không công bố field và kiểm tra authorization |
| Thay đổi semantics nhưng giữ tên field | Client nhận dữ liệu khác kỳ vọng | Tạo field mới và deprecate field cũ |
| Xóa field không kiểm tra consumer | Breaking change ngoài dự kiến | Usage telemetry và schema contract check |

## 27. Quy trình thiết kế schema theo domain

Một quy trình thực tế có thể gồm:

1. Xác định bounded context và owner của từng khái niệm.
2. Thu thập use case đọc và command từ client.
3. Chọn type/field bằng ubiquitous language.
4. Phân biệt domain model, persistence model và GraphQL read model.
5. Xác định aggregate boundary, relationship và snapshot semantics.
6. Tách input/output, định nghĩa nullability, scalar và enum.
7. Thiết kế pagination và error contract cho collection/use case.
8. Xác định field owner, authorization và fetch strategy.
9. Ánh xạ resolver sang application service bằng Spring GraphQL.
10. Kiểm thử contract, security, query count và schema evolution.
11. Review breaking changes trước khi phát hành.

## 28. Nguyên tắc thiết kế schema theo domain

Hãy bắt đầu từ ngôn ngữ và use case của domain, không bắt đầu từ bảng database. Xác định bounded context và owner của từng field; giữ riêng những khái niệm có semantics khác nhau, ngay cả khi chúng cùng tham chiếu một record. Dùng GraphQL type để diễn đạt domain hoặc read model mà client cần, còn JPA entity và domain aggregate tiếp tục phục vụ trách nhiệm nội bộ.

Thiết kế Query theo nhu cầu đọc, Mutation theo hành động nghiệp vụ và Input/Output tách biệt. Đặt nullability theo invariant thật, phân trang collection lớn, định nghĩa error contract và bảo vệ field theo principal/tenant. Trong Spring for GraphQL, giữ resolver mỏng và chuyển xử lý sang application service; dùng @SchemaMapping, DataLoader hoặc @BatchMapping khi cần resolve relationship.

Cuối cùng, xem schema là contract sống: thêm field theo hướng tương thích ngược, deprecate trước khi xóa và kiểm tra breaking change trong CI. Schema theo domain giúp client hiểu đúng nghiệp vụ, đồng thời cho phép hệ thống thay đổi database, service và cách triển khai mà không buộc API thay đổi theo từng chi tiết nội bộ.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
- [GraphQL Specification — Type System](https://spec.graphql.org/)
- [Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
