# Nested input object

Nested input object là cách GraphQL mô tả dữ liệu đầu vào có cấu trúc nhiều cấp. Thay vì gửi một tập argument rời rạc, client gửi một input object chứa các input object con, danh sách hoặc scalar liên quan. Cách thiết kế này phù hợp với mutation nhận một yêu cầu nghiệp vụ có nhiều phần, chẳng hạn tạo đơn hàng cùng địa chỉ giao hàng và các dòng sản phẩm, hoặc tạo sách cùng metadata và danh sách chương.

Trong Spring for GraphQL, các input object được khai báo bằng SDL. GraphQL kiểm tra và chuyển đổi dữ liệu đầu vào theo schema; Spring bind cấu trúc đó vào Java record hoặc DTO thông qua **@Argument**. Các lớp validation và service tiếp tục kiểm tra quy tắc nghiệp vụ, quyền truy cập và tính nhất quán của toàn bộ thao tác.

Bài này tập trung vào cách ghép input object thành cấu trúc lồng nhau, cách truyền variables, quy tắc null/default và list, input đệ quy, binding Java, validation lồng nhau và những giới hạn cần đặt cho payload.

## 1. Khi nào cần nested input object?

Một mutation thường nhận dữ liệu thuộc nhiều nhóm. Ví dụ, khi tạo sách, client có thể cần gửi thông tin sách, metadata và các chương:

~~~graphql
type Mutation {
  createBook(
    title: String!
    language: String
    pageCount: Int
    chapterTitles: [String!]
  ): Book!
}
~~~

Khi cấu trúc đầu vào phát triển, mutation có nhiều argument ở cùng một cấp và không thể hiện rõ nhóm dữ liệu. Ta có thể gom chúng thành các input object riêng:

~~~graphql
input BookMetadataInput {
  language: String
  pageCount: Int
}

input ChapterInput {
  title: String!
  position: Int!
}

input CreateBookInput {
  title: String!
  metadata: BookMetadataInput
  chapters: [ChapterInput!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Ở đây, **CreateBookInput** là input chính; **BookMetadataInput** và **ChapterInput** mô tả các phần con. Cấu trúc này thể hiện rõ mối quan hệ giữa các giá trị và giúp client gửi một yêu cầu hoàn chỉnh.

Nested input hữu ích khi:

- Một thao tác nghiệp vụ nhận nhiều nhóm dữ liệu có cấu trúc riêng.
- Một nhóm field có thể được tái sử dụng trong nhiều input khác nhau.
- Dữ liệu có quan hệ cha-con, ví dụ đơn hàng và dòng đơn hàng.
- Client cần gửi một danh sách các object con.
- Một cấu trúc phân cấp cần được tạo hoặc cập nhật trong cùng một use case.

Không nên lồng object chỉ để làm schema trông có vẻ phân cấp. Hãy dùng cấu trúc lồng khi nó phản ánh ranh giới nghiệp vụ hoặc hình dạng dữ liệu thực sự cần thiết.

## 2. Quy tắc kiểu dữ liệu của input object

Input object được khai báo bằng **input**. Field bên trong input object chỉ được dùng input type:

- Scalar built-in như **String**, **Int**, **Float**, **Boolean**, **ID**.
- Custom scalar đã được đăng ký ở runtime.
- Enum.
- Input object khác.
- List hoặc non-null bọc một input type hợp lệ.

Ví dụ:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
}

input BookMetadataInput {
  language: String
  publishedAt: DateTime
  status: BookStatus = DRAFT
  keywords: [String!]
}
~~~

Một input object không thể chứa object type, interface hoặc union. Những kiểu này là output type. Nếu cần tham chiếu một object đã tồn tại, thông thường client gửi ID:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Server dùng **authorId** để tải tác giả, kiểm tra tác giả có tồn tại và xác minh người dùng có quyền sử dụng tác giả đó. Nếu client cần tạo một object con mới trong cùng mutation, hãy khai báo input type riêng cho object con thay vì dùng output type.

Input field cũng không khai báo argument riêng. Nếu cần truyền tham số cho một thao tác, argument thuộc về field của object type, còn input object chỉ mô tả dữ liệu được gửi.

## 3. Xây dựng cấu trúc lồng nhau

Ví dụ một mutation tạo đơn hàng. Một đơn hàng có địa chỉ giao hàng, thông tin liên hệ và nhiều dòng sản phẩm:

~~~graphql
input AddressInput {
  recipient: String!
  street: String!
  ward: String
  city: String!
  postalCode: String
}

input ContactInput {
  email: String!
  phone: String
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
  note: String
}

input CreateOrderInput {
  shippingAddress: AddressInput!
  contact: ContactInput!
  lines: [OrderLineInput!]!
  customerNote: String
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Input chính **CreateOrderInput** mô tả yêu cầu tạo đơn hàng. Các input con mô tả những nhóm dữ liệu có trách nhiệm riêng:

| Input object | Trách nhiệm |
|---|---|
| **AddressInput** | Địa chỉ nhận hàng |
| **ContactInput** | Thông tin liên hệ cho đơn hàng |
| **OrderLineInput** | Một sản phẩm và số lượng cần đặt |
| **CreateOrderInput** | Gom các phần dữ liệu để tạo đơn hàng |

Client gửi một variables object tương ứng:

~~~json
{
  "input": {
    "shippingAddress": {
      "recipient": "Nguyen An",
      "street": "12 Nguyen Hue",
      "ward": "Ben Nghe",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    },
    "contact": {
      "email": "an@example.com",
      "phone": "0900000000"
    },
    "lines": [
      {
        "productId": "product-01",
        "quantity": 2
      },
      {
        "productId": "product-02",
        "quantity": 1,
        "note": "Giao cùng đơn"
      }
    ],
    "customerNote": "Gọi trước khi giao"
  }
}
~~~

Tên và cấu trúc trong JSON phải khớp với input object trong schema. GraphQL kiểm tra từng cấp; một field con sai kiểu hoặc một field bắt buộc bị thiếu sẽ làm input không hợp lệ trước khi mutation resolver xử lý.

## 4. Truyền nested input bằng variables

Nên dùng variables cho các mutation có cấu trúc lồng nhau. GraphQL document giữ ổn định:

~~~graphql
mutation CreateOrder($input: CreateOrderInput!) {
  createOrder(input: $input) {
    id
    status
    total
  }
}
~~~

Client truyền dữ liệu trong JSON variables. Tách document khỏi variables giúp tái sử dụng operation, tránh nối chuỗi query thủ công và dễ kiểm thử các bộ dữ liệu khác nhau.

Trong GraphQL document, enum được viết dưới dạng enum literal:

~~~graphql
input: {
  status: PUBLISHED
}
~~~

Trong JSON variables, enum được biểu diễn bằng chuỗi:

~~~json
{
  "status": "PUBLISHED"
}
~~~

Các giá trị scalar trong nested object được coercion theo đúng scalar tương ứng. Ví dụ **DateTime** cần có scalar implementation để parse/serialize ngày giờ; chỉ khai báo **scalar DateTime** trong SDL là chưa đủ.

### Field không xác định

Input object chỉ nhận những field đã khai báo. Nếu client gửi:

~~~json
{
  "input": {
    "shippingAddress": {
      "recipient": "Nguyen An",
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City",
      "countryCode": "VN"
    },
    "lines": []
  }
}
~~~

Nếu **countryCode** không có trong **AddressInput**, GraphQL báo lỗi input coercion/validation. Điều này ngăn client vô tình gửi những thuộc tính mà server không công khai.

### List input và singleton coercion

Field list thường được gửi dưới dạng JSON array. GraphQL input coercion cũng cho phép một giá trị đơn được chuyển thành danh sách một phần tử trong một số trường hợp theo quy tắc list input:

~~~graphql
input CreateBookInput {
  tags: [String!]
}
~~~

Với field **tags**, client nên gửi array như **["graphql"]** để payload thể hiện rõ ý định. Không nên phụ thuộc vào singleton coercion trong hợp đồng client nếu dữ liệu nghiệp vụ vốn là danh sách.

## 5. List và nullability ở nhiều cấp

Nested input có thể có nhiều lớp nullable và non-null. Mỗi dấu **!** áp dụng tại vị trí mà nó bọc.

Với field:

~~~graphql
input CreateOrderInput {
  lines: [OrderLineInput!]!
}
~~~

Ý nghĩa:

- **lines** không được null.
- Danh sách **lines** có thể rỗng, trừ khi validation nghiệp vụ quy định phải có phần tử.
- Từng phần tử **OrderLineInput** không được null.
- Các field bên trong mỗi **OrderLineInput** tiếp tục có quy tắc nullability riêng.

So sánh bốn dạng list:

| Khai báo | List null? | Phần tử null? |
|---|---:|---:|
| **[OrderLineInput]** | Có | Có |
| **[OrderLineInput]!** | Không | Có |
| **[OrderLineInput!]** | Có | Không |
| **[OrderLineInput!]!** | Không | Không |

Ví dụ:

~~~graphql
input OrderLineInput {
  productId: ID!
  quantity: Int!
  discountCode: String
}
~~~

Danh sách không null và từng dòng không null không có nghĩa mọi field trong dòng đều bắt buộc. **discountCode** vẫn có thể bị bỏ qua hoặc là null.

GraphQL không có cú pháp trực tiếp để nói một list phải có ít nhất một phần tử. Nếu đơn hàng phải chứa ít nhất một dòng, hãy kiểm tra trong Bean Validation hoặc service layer.

## 6. Default value trong input lồng nhau

Input field có thể khai báo default value. Default được áp dụng khi field bị bỏ qua, theo quy tắc GraphQL:

~~~graphql
enum DeliveryMethod {
  STANDARD
  EXPRESS
}

input DeliveryOptionsInput {
  method: DeliveryMethod = STANDARD
  leaveAtDoor: Boolean = false
}

input CreateOrderInput {
  shippingAddress: AddressInput!
  lines: [OrderLineInput!]!
  delivery: DeliveryOptionsInput = {
    method: STANDARD
    leaveAtDoor: false
  }
}
~~~

Nếu client bỏ qua **delivery**, default input object được dùng. Nếu client gửi **delivery** với một object nhưng bỏ qua **leaveAtDoor**, default của field con có thể được áp dụng. Nếu client gửi tường minh **delivery: null**, field nullable nhận null thay vì default object.

Cần phân biệt:

| Payload | Kết quả theo schema |
|---|---|
| Bỏ qua **delivery** | Dùng default của field **delivery** |
| Gửi **delivery: null** | Giá trị **delivery** là null nếu field nullable |
| Gửi **delivery: {}** | Input object có mặt; các field con dùng default nếu có |
| Gửi **delivery: { method: EXPRESS }** | **method** là EXPRESS; field con khác dùng default nếu có |

Default nên dùng cho những giá trị có ý nghĩa ổn định và dễ hiểu. Không nên đặt default cho dữ liệu phụ thuộc người dùng hiện tại, thời điểm, tenant hoặc trạng thái database vì schema default là giá trị tĩnh được định nghĩa trong schema.

## 7. Phân biệt omitted và null trong nested input

Với mutation cập nhật một phần, hai trạng thái “không gửi field” và “gửi field với null” có thể mang ý nghĩa khác nhau:

- Omitted: giữ nguyên giá trị hiện tại.
- Null: xóa hoặc đặt giá trị thành null, nếu nghiệp vụ cho phép.

Ví dụ:

~~~graphql
input UpdateAddressInput {
  street: String
  ward: String
  city: String
}

input UpdateCustomerInput {
  id: ID!
  address: UpdateAddressInput
}
~~~

Payload chỉ gửi **city**:

~~~json
{
  "input": {
    "id": "customer-01",
    "address": {
      "city": "Ho Chi Minh City"
    }
  }
}
~~~

Ở đây **street** và **ward** bị bỏ qua. Nếu client gửi **ward: null**, server có thể hiểu là yêu cầu xóa ward. Nhưng nếu **address** bị bỏ qua hoàn toàn và nếu **address: null**, hai trạng thái đó cũng có thể có ý nghĩa khác nhau.

Một DTO Java thông thường có thể không giữ được thông tin field có xuất hiện hay không: field bị bỏ qua và field được truyền null có thể cùng thành Java null. Nếu cần patch semantics chính xác, có thể bind vào cấu trúc Map để kiểm tra key có tồn tại, dùng kiểu presence-aware phù hợp ở ranh giới argument, hoặc thiết kế mutation riêng cho thao tác xóa. Cần kiểm tra cách bind của phiên bản Spring GraphQL đang sử dụng, nhất là với input object lồng nhiều cấp.

Không nên tự suy ra rằng mọi null trong input đều có nghĩa “giữ nguyên”. Hãy ghi rõ hợp đồng API và kiểm thử cả trường hợp omitted lẫn explicit null.

## 8. Input object đệ quy

Một input object có thể tham chiếu một input object khác và có thể tạo cấu trúc đệ quy. Ví dụ biểu diễn cây danh mục:

~~~graphql
input CategoryInput {
  name: String!
  children: [CategoryInput!]
}

input CreateCategoryTreeInput {
  root: CategoryInput!
}

type Mutation {
  createCategoryTree(input: CreateCategoryTreeInput!): Category!
}
~~~

Client có thể gửi một cây nhiều cấp:

~~~json
{
  "input": {
    "root": {
      "name": "Books",
      "children": [
        {
          "name": "Programming",
          "children": [
            {
              "name": "GraphQL"
            },
            {
              "name": "Spring"
            }
          ]
        },
        {
          "name": "Databases"
        }
      ]
    }
  }
}
~~~

GraphQL cho phép input type tham chiếu đệ quy nếu cấu trúc có điểm kết thúc. Một chuỗi vòng lặp chỉ gồm các field non-null đơn lẻ bắt buộc không có điểm dừng là không hợp lệ, vì không thể tạo một giá trị hữu hạn thỏa mãn cấu trúc đó. Có thể ngắt chuỗi bằng field nullable hoặc list.

Ví dụ sau tạo chuỗi non-null đơn lẻ không thể kết thúc:

~~~graphql
input NodeInput {
  next: NodeInput!
}
~~~

Một cấu trúc có điểm kết thúc hợp lệ:

~~~graphql
input NodeInput {
  value: String!
  next: NodeInput
}
~~~

Khi nhận dữ liệu đệ quy, server cần đặt giới hạn độ sâu, số node và tổng kích thước payload. Schema hợp lệ không đồng nghĩa payload bất kỳ đều có chi phí xử lý chấp nhận được.

## 9. Bind nested input vào Java trong Spring for GraphQL

Spring for GraphQL bind input object vào tham số Java của controller thông qua **@Argument**. Có thể biểu diễn các cấp input bằng record lồng nhau.

SDL:

~~~graphql
input AddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
  note: String
}

input CreateOrderInput {
  shippingAddress: AddressInput!
  lines: [OrderLineInput!]!
  customerNote: String
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Java records:

~~~java
public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record OrderLineInput(
        String productId,
        Integer quantity,
        String note) {
}

public record CreateOrderInput(
        AddressInput shippingAddress,
        List<OrderLineInput> lines,
        String customerNote) {
}
~~~

Controller:

~~~java
@Controller
public class OrderMutationController {

    private final OrderService orderService;

    public OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order createOrder(@Argument("input") CreateOrderInput input) {
        CreateOrderCommand command = new CreateOrderCommand(
                input.shippingAddress(),
                input.lines(),
                input.customerNote());

        return orderService.create(command);
    }
}
~~~

**@Argument("input")** lấy argument **input** của field mutation và bind cấu trúc lồng nhau vào record. Các tên field Java cần tương thích với input field trong SDL. Kiểu Java cũng cần phù hợp: **ID** thường dùng **String**, **Int** dùng **Integer** hoặc kiểu số phù hợp, list dùng collection và input con dùng record/DTO tương ứng.

Nên cân nhắc chuyển GraphQL input DTO thành command của application layer. Điều đó giúp service không phụ thuộc vào cấu trúc API, đồng thời cho phép adapter khác sử dụng cùng nghiệp vụ.

### Khi nào dùng Map thay cho DTO?

DTO/record phù hợp khi cấu trúc input đã biết và ổn định. Map có thể hữu ích khi:

- Cần kiểm tra một field có được gửi hay không.
- Có một vùng dữ liệu mở với cấu trúc được kiểm soát riêng.
- Cần xử lý explicit null khác với omitted.

Không nên dùng Map cho toàn bộ input chỉ vì nó linh hoạt. Map làm giảm lợi ích về kiểu tĩnh, refactor và tài liệu schema. Dù bind vào Map, schema GraphQL vẫn nên định nghĩa rõ input field được phép nhận.

## 10. Validation cho input lồng nhau

GraphQL kiểm tra kiểu dữ liệu ở mọi cấp input. Ví dụ, nếu **quantity** là **Int!**, client không thể gửi chuỗi thay cho số nguyên hoặc bỏ qua field bắt buộc. Tuy nhiên, GraphQL không tự kiểm tra quantity phải lớn hơn 0 hay product ID có tồn tại.

### Bean Validation với nested object

Có thể dùng Jakarta Bean Validation để kiểm tra các cấp input:

~~~java
public record AddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        @Pattern(regexp = "\\d{6}") String postalCode) {
}

public record OrderLineInput(
        @NotBlank String productId,
        @NotNull @Min(1) Integer quantity,
        @Size(max = 200) String note) {
}

public record CreateOrderInput(
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLineInput> lines,
        @Size(max = 500) String customerNote) {
}
~~~

Các điểm cần chú ý:

- **@Valid** trên **shippingAddress** kích hoạt cascade validation cho object con.
- **@Valid** trên phần tử list giúp kiểm tra từng **OrderLineInput**.
- **@NotEmpty** yêu cầu list có ít nhất một phần tử.
- **@NotNull** trên phần tử list ngăn phần tử null ở tầng Bean Validation.
- **@Min(1)** bảo đảm số lượng lớn hơn hoặc bằng 1.

Controller có thể đánh dấu input cần validation:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Ứng dụng cần có Jakarta Bean Validation provider, thường qua **spring-boot-starter-validation**. Với Spring Boot 3, dùng các annotation trong **jakarta.validation**. Hãy xác nhận cấu hình method/argument validation của ứng dụng để constraint được thực thi ở đúng cấp.

### Business validation cho toàn bộ cây input

Một số quy tắc cần kiểm tra dữ liệu hoặc nhiều phần tử cùng lúc:

- Tất cả product ID có tồn tại và đang được bán không?
- Người dùng có quyền mua các sản phẩm đó không?
- Tổng số lượng có vượt giới hạn đơn hàng không?
- Có product ID trùng nhau cần gộp thành một dòng không?
- Địa chỉ có thuộc khu vực giao hàng hỗ trợ không?
- Các dòng hàng và địa chỉ có thể được xử lý trong cùng một giao dịch không?

Những quy tắc này nên nằm trong service/application layer. Validation tại controller giúp phản hồi lỗi đầu vào sớm; service vẫn phải bảo vệ invariant nghiệp vụ vì cùng service có thể được gọi từ nhiều đường vào khác nhau.

## 11. Bảo mật khi nhận dữ liệu nhiều cấp

Nested input có thể mở rộng bề mặt dữ liệu client gửi. Nếu thiết kế không cẩn thận, client có thể thay đổi các thuộc tính mà server phải quản lý.

Ví dụ không nên nhận các field nội bộ sau nếu chúng do server quyết định:

~~~graphql
input CreateOrderInput {
  customerId: ID
  status: String
  approved: Boolean
  total: Float
  shippingAddress: AddressInput
  lines: [OrderLineInput!]!
}
~~~

Server nên lấy **customerId** từ principal đã xác thực, tính **total** từ giá sản phẩm và số lượng, đặt **status** theo workflow và thực hiện phê duyệt bằng quy trình riêng. Không nên tin các giá trị do client gửi chỉ vì chúng đúng kiểu GraphQL.

Với nested input, cần:

- Xác minh quyền trên từng ID tham chiếu ở mọi cấp.
- Không cho client tự chọn tenant, owner hoặc role nếu server phải quyết định.
- Giới hạn độ sâu và số lượng object con.
- Giới hạn độ dài chuỗi, kích thước list và tổng payload.
- Tránh log toàn bộ input nếu chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.
- Kiểm tra transaction khi một mutation tạo nhiều object liên quan.
- Xác định rõ chính sách khi một phần tử trong list không hợp lệ: từ chối toàn bộ hay cho phép kết quả từng phần.

GraphQL input coercion bảo vệ cấu trúc và kiểu; authorization cùng business validation bảo vệ dữ liệu và quyền nghiệp vụ.

## 12. Transaction và tính nhất quán khi tạo object lồng nhau

Một mutation nhận nested input có thể tạo nhiều bản ghi: đơn hàng, địa chỉ, dòng đơn hàng và các liên kết sản phẩm. Nếu chỉ một phần được lưu thành công, hệ thống có thể để lại dữ liệu dở dang.

Ví dụ service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AddressRepository addressRepository;
    private final ProductService productService;

    public OrderService(
            OrderRepository orderRepository,
            AddressRepository addressRepository,
            ProductService productService) {
        this.orderRepository = orderRepository;
        this.addressRepository = addressRepository;
        this.productService = productService;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        Address address = addressRepository.save(
                Address.from(command.shippingAddress()));

        List<OrderLine> lines = command.lines().stream()
                .map(line -> {
                    Product product =
                            productService.requirePurchasable(line.productId());
                    return OrderLine.create(product, line.quantity(), line.note());
                })
                .toList();

        Order order = Order.create(address, lines, command.customerNote());
        return orderRepository.save(order);
    }
}
~~~

Đây là ví dụ minh họa về ranh giới giao dịch. Trong ứng dụng thực tế, việc gọi service bên ngoài có thể không nằm trong cùng transaction database; khi đó cần cân nhắc outbox, saga hoặc cơ chế bù trừ phù hợp. Không nên để GraphQL resolver tự điều phối nhiều repository và transaction nếu đó là logic nghiệp vụ của service.

## 13. Kiểm thử nested input với GraphQlTester

GraphQlTester cho phép gửi variables lồng nhau dưới dạng Map và List:

~~~java
graphQlTester.document("""
        mutation CreateOrder($input: CreateOrderInput!) {
            createOrder(input: $input) {
                id
                status
            }
        }
        """)
    .variable("input", Map.of(
            "shippingAddress", Map.of(
                    "recipient", "Nguyen An",
                    "street", "12 Nguyen Hue",
                    "city", "Ho Chi Minh City"),
            "lines", List.of(
                    Map.of("productId", "product-01", "quantity", 2),
                    Map.of("productId", "product-02", "quantity", 1))))
    .execute()
    .path("createOrder.status")
    .entity(String.class)
    .isEqualTo("CREATED");
~~~

Test nên bao gồm:

1. Input lồng đầy đủ tạo được object cha và các object con.
2. Thiếu nested object non-null bị GraphQL từ chối.
3. Field con sai kiểu hoặc không tồn tại bị coercion/validation từ chối.
4. List rỗng và list có phần tử được xử lý theo quy tắc nghiệp vụ.
5. Một phần tử list không hợp lệ làm kết quả đúng với chính sách toàn bộ mutation.
6. Bean Validation được áp dụng ở các cấp lồng nhau.
7. Omitted và explicit null có hành vi khác nhau nếu hợp đồng yêu cầu.
8. Input đệ quy sâu hoặc payload quá lớn bị giới hạn.
9. ID ở nested input được kiểm tra quyền và sự tồn tại.
10. Lỗi giữa quá trình lưu nhiều object không để lại trạng thái dở dang.

Có thể kiểm tra lỗi bằng **errors()** của GraphQlTester và kiểm tra phần **data** khi API hỗ trợ partial result. Với mutation có tính nguyên tử, test cần xác nhận dữ liệu không được lưu một phần khi thao tác thất bại.

## 14. Những lỗi thiết kế nested input thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng output object type bên trong input | Schema không hợp lệ | Tạo input object riêng |
| Lồng quá nhiều cấp không có ý nghĩa nghiệp vụ | Client khó tạo payload và server khó validate | Chỉ tách nhóm dữ liệu có trách nhiệm rõ ràng |
| Tạo input type tổng quát dùng cho mọi mutation | Quyền thay đổi và required fields không rõ | Thiết kế input theo use case |
| Không kiểm tra nullability ở từng cấp | Có thể nhận cấu trúc thiếu hoặc phần tử null ngoài ý muốn | Chọn dấu non-null theo hợp đồng |
| Cho list rỗng dù nghiệp vụ yêu cầu phần tử | Mutation tạo object không đầy đủ | Dùng Bean Validation hoặc business validation |
| Giả định omitted và null giống nhau | Patch update có thể xóa dữ liệu ngoài ý muốn | Giữ thông tin presence khi cần |
| Chỉ kiểm tra kiểu GraphQL | Bỏ sót ID không tồn tại hoặc quyền truy cập | Kiểm tra trong service |
| Cho phép payload đệ quy không giới hạn | Có thể tiêu tốn CPU, memory và database | Giới hạn depth, node count và payload size |
| Lưu object con từng phần không có transaction | Dữ liệu có thể không nhất quán | Xác định transaction hoặc quy trình bù trừ |
| Dùng Map cho mọi input | Mất lợi ích kiểu tĩnh và khó refactor | Dùng record/DTO cho cấu trúc đã biết |

## 15. Quy trình thiết kế nested input object

Khi thiết kế một mutation nhận cấu trúc lồng nhau, hãy thực hiện:

1. Xác định use case và các nhóm dữ liệu client cần gửi.
2. Tạo input object riêng cho từng nhóm có ý nghĩa nghiệp vụ.
3. Chỉ dùng scalar, enum, input object và list trong input field.
4. Chọn nullability và default cho từng cấp, bao gồm từng phần tử list.
5. Quyết định field nào tham chiếu tài nguyên hiện có bằng ID, field nào tạo object con mới.
6. Xác định ý nghĩa của omitted, null và default đối với mutation cập nhật.
7. Bind input vào Java record/DTO lồng nhau bằng **@Argument**.
8. Áp dụng Bean Validation cascade và business validation.
9. Kiểm tra authorization, kích thước payload, độ sâu và transaction.
10. Viết GraphQlTester cho trường hợp thành công, lỗi cấu trúc, null, list và input sâu.

Nested input object giúp biểu diễn một yêu cầu nghiệp vụ nhiều thành phần bằng một hợp đồng GraphQL rõ ràng. SDL định nghĩa cấu trúc và kiểu; GraphQL kiểm tra dữ liệu ở mọi cấp; Spring for GraphQL bind thành Java object; validation và service layer bảo đảm dữ liệu hợp lệ, có quyền và được lưu nhất quán. Khi cấu trúc lồng nhau phản ánh đúng miền nghiệp vụ và có giới hạn tài nguyên phù hợp, mutation sẽ dễ hiểu, dễ kiểm thử và an toàn hơn khi mở rộng.
