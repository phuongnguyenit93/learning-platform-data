# Mutation input object

## Mục tiêu

Sau bài học này, bạn có thể:

- Thiết kế input object trong GraphQL SDL cho các mutation.
- Giải thích vì sao input type tách biệt với object type dùng trong response.
- Bind input object vào Java record hoặc class bằng @Argument trong Spring for GraphQL.
- Xử lý input lồng nhau, danh sách, enum và custom scalar.
- Kết hợp Bean Validation với kiểm tra nghiệp vụ trong service.
- Thiết kế input cho create và update, bao gồm khác biệt giữa field bị bỏ qua và field có giá trị null.
- Kiểm thử mutation với variables và GraphQlTester.

## Vì sao mutation nên nhận input object?

Mutation thường thực hiện một use case có nhiều dữ liệu đầu vào. Ví dụ tạo đơn hàng cần mã khách hàng, danh sách sản phẩm, địa chỉ giao hàng và ghi chú. Nếu khai báo tất cả thành argument riêng, schema sẽ có nhiều tham số và khó mở rộng:

~~~graphql
type Mutation {
  createOrder(
    customerId: ID!
    productIds: [ID!]!
    quantities: [Int!]!
    recipient: String!
    street: String!
    city: String!
    note: String
  ): Order!
}
~~~

Thiết kế này còn có nguy cơ ghép nhầm các list productIds và quantities theo vị trí. Thay vào đó, hãy gom dữ liệu liên quan vào một input object:

~~~graphql
type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}

input CreateOrderInput {
  customerId: ID!
  items: [CreateOrderItemInput!]!
  shippingAddress: ShippingAddressInput!
  note: String
}

input CreateOrderItemInput {
  productId: ID!
  quantity: Int!
}

input ShippingAddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}
~~~

Input object tạo ra một cấu trúc có tên, có thể tái sử dụng và dễ phát triển. Mỗi phần tử trong items mang productId cùng quantity, nên dữ liệu của một dòng hàng luôn đi cùng nhau. Địa chỉ giao hàng cũng được nhóm thành một object riêng.

Đây là quy ước thiết kế hữu ích cho mutation có nhiều dữ liệu đầu vào. GraphQL không bắt buộc mọi mutation chỉ có một argument input, nhưng một input object thường giúp schema rõ ràng và dễ mở rộng.

## Input object khác object type trong response

GraphQL phân biệt type dùng để trả dữ liệu với input type dùng để nhận dữ liệu:

| Loại | Từ khóa SDL | Vai trò |
| --- | --- | --- |
| Object type | type | Mô tả field client có thể truy vấn trong response |
| Input object | input | Mô tả field client được phép gửi vào argument |

Ví dụ object type Order có thể chứa thông tin chỉ đọc hoặc dữ liệu được tính ở server:

~~~graphql
type Order {
  id: ID!
  status: OrderStatus!
  total: BigDecimal!
  createdAt: DateTime!
  items: [OrderItem!]!
}
~~~

Input để tạo đơn hàng chỉ nên chứa dữ liệu client được phép cung cấp:

~~~graphql
input CreateOrderInput {
  customerId: ID!
  items: [CreateOrderItemInput!]!
  shippingAddress: ShippingAddressInput!
  note: String
}
~~~

Không dùng object type Order làm kiểu input. GraphQL chỉ cho phép input object chứa scalar, enum, input object khác và list/non-null modifier hợp lệ. Interface, union và object type là các kiểu output, không thể đặt trực tiếp trong input object.

Tách input và output giúp server kiểm soát dữ liệu đầu vào. Client không được tự gửi status, total hoặc createdAt nếu những field đó do nghiệp vụ quyết định.

## Khai báo mutation và input object trong SDL

Một schema đơn giản cho chức năng tạo sản phẩm có thể được khai báo như sau:

~~~graphql
enum ProductCategory {
  BOOK
  ELECTRONICS
  HOME
}

input CreateProductInput {
  name: String!
  description: String
  category: ProductCategory!
  price: BigDecimal!
  tagIds: [ID!]!
}

type Product {
  id: ID!
  name: String!
  description: String
  category: ProductCategory!
  price: BigDecimal!
  tags: [Tag!]!
}

type Mutation {
  createProduct(input: CreateProductInput!): Product!
}
~~~

Các dấu ! xác định giá trị bắt buộc:

- createProduct yêu cầu argument input.
- CreateProductInput yêu cầu name, category, price và tagIds.
- description có thể bị bỏ qua hoặc nhận null.
- tagIds phải là một list khác null và từng phần tử không được null. List rỗng vẫn hợp lệ về mặt kiểu; nếu nghiệp vụ yêu cầu ít nhất một tag, cần thêm validation.

SDL kiểm tra cấu trúc và kiểu GraphQL. Nó không tự bảo đảm giá phải lớn hơn 0, tag có tồn tại hoặc người dùng có quyền tạo sản phẩm trong category đã chọn.

## Gửi mutation bằng variables

Client nên dùng variables để tách dữ liệu đầu vào khỏi cấu trúc operation:

~~~graphql
mutation CreateProduct($input: CreateProductInput!) {
  createProduct(input: $input) {
    id
    name
    category
    price
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "name": "Bàn phím cơ",
    "description": "Bàn phím layout 75%",
    "category": "ELECTRONICS",
    "price": 1850000.00,
    "tagIds": ["tag-01", "tag-07"]
  }
}
~~~

GraphQL kiểm tra variables theo CreateProductInput trước khi gọi resolver. Field thừa không được khai báo trong input type sẽ bị từ chối; field bắt buộc bị thiếu hoặc có kiểu không hợp lệ cũng khiến request không qua bước input coercion.

Variables thuận tiện cho client vì có thể tái sử dụng operation, cache operation document và truyền dữ liệu phức tạp mà không phải ghép chuỗi GraphQL ở runtime.

## Bind input object vào Java record

Spring for GraphQL cung cấp argument binding để chuyển dữ liệu input thành kiểu Java. Với annotated controller, dùng @Argument để nhận toàn bộ input object.

Record là lựa chọn phù hợp cho DTO bất biến:

~~~java
import java.math.BigDecimal;
import java.util.List;

public record CreateProductInput(
        String name,
        String description,
        ProductCategory category,
        BigDecimal price,
        List<String> tagIds) {
}
~~~

Enum Java tương ứng:

~~~java
public enum ProductCategory {
    BOOK,
    ELECTRONICS,
    HOME
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductMutationController {

    private final ProductService productService;

    public ProductMutationController(ProductService productService) {
        this.productService = productService;
    }

    @MutationMapping
    public Product createProduct(
            @Argument("input") CreateProductInput input) {
        return productService.create(input);
    }
}
~~~

Tên component của record cần tương ứng với tên field trong SDL. Kiểu Java cũng phải tương thích với scalar hoặc enum được GraphQL runtime chuyển đổi. Ví dụ BigDecimal phù hợp với scalar BigDecimal đã được đăng ký; nếu dùng custom scalar khác, hãy kiểm tra Java type mà scalar đó tạo ra.

Không nên dùng kiểu nguyên thủy cho thuộc tính input nullable. Dùng Integer, Boolean hoặc BigDecimal thay vì int, boolean cho field có thể nhận null. Kiểu tham chiếu cho phép DTO biểu diễn được trường hợp không có giá trị.

## Bind input object lồng nhau và danh sách

Input object có thể chứa các input object khác. Ví dụ đơn hàng có địa chỉ giao hàng và nhiều dòng hàng:

~~~java
public record ShippingAddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record CreateOrderItemInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        String customerId,
        List<CreateOrderItemInput> items,
        ShippingAddressInput shippingAddress,
        String note) {
}
~~~

Controller nhận DTO cấp cao nhất:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Argument binder ánh xạ các field lồng nhau theo cấu trúc tương ứng. items trở thành List<CreateOrderItemInput>, còn shippingAddress trở thành ShippingAddressInput. Service nhận một object có kiểu rõ ràng thay vì phải tự đọc các Map lồng nhau.

Khi thiết kế list, hãy xác định rõ nullability ở cả cấp list và phần tử:

| SDL | Ý nghĩa |
| --- | --- |
| [ID] | List có thể null; phần tử có thể null |
| [ID!] | List có thể null; phần tử không được null |
| [ID]! | List không được null; phần tử có thể null |
| [ID!]! | List không được null; phần tử không được null |

Nullability không thay thế validation nghiệp vụ. Ví dụ [CreateOrderItemInput!]! vẫn cho phép list rỗng. Dùng @NotEmpty nếu đơn hàng bắt buộc có ít nhất một dòng hàng.

## Bind enum và custom scalar

Input object có thể chứa enum và custom scalar. Với enum, giá trị GraphQL phải khớp một trong các enum value được khai báo:

~~~graphql
enum PaymentMethod {
  CASH
  CARD
  BANK_TRANSFER
}

input PaymentInput {
  method: PaymentMethod!
  amount: BigDecimal!
}
~~~

Java DTO:

~~~java
public enum PaymentMethod {
    CASH,
    CARD,
    BANK_TRANSFER
}

public record PaymentInput(
        PaymentMethod method,
        BigDecimal amount) {
}
~~~

Với custom scalar như DateTime, UUID hoặc BigDecimal mở rộng, cần đăng ký implementation bằng RuntimeWiringConfigurer và dùng Java type tương thích trong DTO. Nếu scalar parse thành OffsetDateTime, không nên khai báo field Java là LocalDateTime rồi giả định binder sẽ tự bỏ offset. Hãy thống nhất kiểu dữ liệu giữa SDL, scalar implementation và DTO.

## Dùng class DTO thay cho record

Nếu dự án dùng JavaBean hoặc cần setter, có thể khai báo input DTO bằng class:

~~~java
public class CreateProductInput {

    private String name;
    private String description;
    private ProductCategory category;
    private BigDecimal price;
    private List<String> tagIds;

    public CreateProductInput() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public ProductCategory getCategory() {
        return category;
    }

    public void setCategory(ProductCategory category) {
        this.category = category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public List<String> getTagIds() {
        return tagIds;
    }

    public void setTagIds(List<String> tagIds) {
        this.tagIds = tagIds;
    }
}
~~~

Class DTO có thể dùng constructor binding hoặc property binding tùy cấu trúc và cách cấu hình binder. Giữ constructor, tên property và kiểu dữ liệu đơn giản để việc bind dễ dự đoán. Không tạo nhiều constructor cạnh tranh nếu không có lý do rõ ràng.

## Validation cho mutation input

GraphQL schema kiểm tra kiểu, field bắt buộc và enum. Bean Validation bổ sung các ràng buộc dữ liệu như chuỗi không rỗng, số dương hoặc danh sách không rỗng.

Thêm validation dependency nếu dự án chưa có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Định nghĩa DTO với các constraint:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderInput(
        @NotBlank String customerId,
        @NotEmpty List<@NotNull @Valid CreateOrderItemInput> items,
        @NotNull @Valid ShippingAddressInput shippingAddress,
        String note) {
}

public record CreateOrderItemInput(
        @NotBlank String productId,
        @NotNull @Positive Integer quantity) {
}

public record ShippingAddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        String postalCode) {
}
~~~

Annotation @Valid cho phép validation cascade vào object lồng nhau và phần tử của list. Controller kích hoạt validation cho input:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Validation cần được đặt ở đúng tầng:

| Tầng | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| GraphQL schema | customerId là ID!, quantity là Int! | Kiểm tra cấu trúc, kiểu và nullability |
| Bean Validation | quantity phải dương, recipient không rỗng | Kiểm tra ràng buộc dữ liệu cục bộ |
| Application service/domain | Customer phải tồn tại, sản phẩm còn bán, tag thuộc tenant hiện tại | Kiểm tra trạng thái và quy tắc nghiệp vụ |

Không thể dùng Bean Validation để thay thế kiểm tra quyền. Ví dụ customerId có định dạng hợp lệ không có nghĩa người dùng hiện tại được phép tạo đơn hàng cho customer đó.

Khi validation thất bại, Spring for GraphQL chuyển lỗi binding/validation thành GraphQL error theo cơ chế xử lý lỗi của framework. Nếu API cần định dạng lỗi thống nhất, có thể bổ sung DataFetcherExceptionResolver để ánh xạ lỗi nghiệp vụ sang thông tin client được phép nhận. Không đưa stack trace, câu SQL hoặc dữ liệu nội bộ vào thông điệp lỗi.

## Input object cho create và update

Input của thao tác tạo thường có các field bắt buộc vì server cần dữ liệu để tạo tài nguyên:

~~~graphql
input CreateProductInput {
  name: String!
  category: ProductCategory!
  price: BigDecimal!
}
~~~

Input của thao tác cập nhật một phần thường có field nullable để client chỉ gửi những giá trị muốn thay đổi:

~~~graphql
input UpdateProductInput {
  name: String
  description: String
  price: BigDecimal
}

type Mutation {
  updateProduct(id: ID!, input: UpdateProductInput!): Product!
}
~~~

Ví dụ client chỉ cập nhật tên:

~~~graphql
mutation UpdateProduct($id: ID!, $input: UpdateProductInput!) {
  updateProduct(id: $id, input: $input) {
    id
    name
    description
  }
}
~~~

Variables:

~~~json
{
  "id": "product-101",
  "input": {
    "name": "Bàn phím cơ không dây"
  }
}
~~~

Field description bị bỏ qua. Một API patch thường quy ước field bị bỏ qua là giữ nguyên giá trị hiện tại, còn explicit null là xóa giá trị nếu field đó cho phép xóa.

### Phân biệt omitted và explicit null

Nếu DTO chỉ có thuộc tính nullable thông thường như String description, giá trị omitted và giá trị null tường minh có thể cùng được bind thành null. Nếu nghiệp vụ cần phân biệt hai trạng thái, Spring for GraphQL cung cấp ArgumentValue<T> để giữ lại thông tin field có bị omitted hay không.

Ví dụ DTO cập nhật:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import java.math.BigDecimal;

public record UpdateProductInput(
        ArgumentValue<String> name,
        ArgumentValue<String> description,
        ArgumentValue<BigDecimal> price) {
}
~~~

Service có thể xử lý từng field:

~~~java
public Product update(String id, UpdateProductInput input) {
    Product current = productRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));

    if (!input.name().isOmitted()) {
        current.setName(input.name().value());
    }
    if (!input.description().isOmitted()) {
        current.setDescription(input.description().value());
    }
    if (!input.price().isOmitted()) {
        current.setPrice(input.price().value());
    }

    return productRepository.save(current);
}
~~~

Trong ví dụ, description bị omitted thì giữ nguyên; description explicit null thì xóa giá trị. Với name và price, service cần từ chối null theo quy tắc nghiệp vụ trước khi lưu. Có thể kết hợp validation hoặc kiểm tra tường minh để bảo đảm dữ liệu hợp lệ.

Nếu use case không cần phân biệt omitted với null, DTO nullable thông thường đơn giản hơn. Khi dùng ArgumentValue trong input object lồng nhau, hãy kiểm thử binding trên phiên bản Spring for GraphQL của dự án để xác nhận semantics thực tế.

### Default value trong input object

GraphQL cho phép khai báo default cho field input:

~~~graphql
input SearchProductsInput {
  page: Int = 0
  size: Int! = 20
  keyword: String
}
~~~

Nếu page hoặc size bị bỏ qua, GraphQL áp dụng default. Nếu field nullable keyword bị bỏ qua, nó không có giá trị được cung cấp. Nếu client gửi keyword: null, giá trị vẫn là null; default chỉ được áp dụng khi field bị bỏ qua, không thay thế explicit null.

Chọn default trong SDL khi giá trị đó là quy tắc chung của API. Nếu default phụ thuộc vào tenant, quyền hoặc cấu hình runtime, hãy tính trong service thay vì khai báo cứng trong schema.

## Thiết kế response của mutation

Mutation có thể trả trực tiếp object vừa tạo hoặc trả một payload type chứa object và metadata. Với API nhỏ, trả trực tiếp Product là đơn giản:

~~~graphql
type Mutation {
  createProduct(input: CreateProductInput!): Product!
}
~~~

Với API cần thêm thông tin như mã yêu cầu, trạng thái xử lý hoặc danh sách lỗi nghiệp vụ có cấu trúc, có thể dùng payload:

~~~graphql
type CreateProductPayload {
  product: Product
  requestId: ID!
}

type Mutation {
  createProduct(input: CreateProductInput!): CreateProductPayload!
}
~~~

Payload là output object type, không phải input object. Client có thể chọn các field cần nhận:

~~~graphql
mutation CreateProduct($input: CreateProductInput!) {
  createProduct(input: $input) {
    requestId
    product {
      id
      name
    }
  }
}
~~~

Chọn response shape dựa trên nhu cầu client và quy ước lỗi của API. Không cần tạo payload wrapper cho mọi mutation nếu nó không mang thêm giá trị.

## Ranh giới transaction và thực thi mutation

Root mutation field trong một operation được GraphQL thực thi tuần tự. Tuy nhiên, điều đó không tự bảo đảm nhiều mutation field trong cùng operation nằm trong một database transaction hoặc được rollback cùng nhau.

Nếu use case cần tính nguyên tử, hãy gom các bước nghiệp vụ vào một application service và đặt transaction ở tầng đó. Ví dụ tạo đơn hàng có thể cần kiểm tra tồn kho, tạo order và ghi order items trong cùng transaction. Không dựa vào việc client gửi nhiều mutation field trong một request để thay thế transaction nghiệp vụ.

Tương tự, controller nên làm nhiệm vụ nhận input, gọi service và trả kết quả. Quy tắc tính giá, kiểm tra tồn kho, phân quyền và ghi dữ liệu thuộc application/domain layer.

## Kiểm thử mutation input bằng GraphQlTester

GraphQlTester cho phép gửi document và variables, sau đó kiểm tra response. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

graphQlTester.document("""
        mutation CreateProduct($input: CreateProductInput!) {
            createProduct(input: $input) {
                id
                name
                category
            }
        }
        """)
    .variable("input", Map.of(
            "name", "Bàn phím cơ",
            "category", "ELECTRONICS",
            "price", new BigDecimal("1850000.00"),
            "tagIds", List.of("tag-01", "tag-07")))
    .execute()
    .path("createProduct.name")
    .entity(String.class)
    .isEqualTo("Bàn phím cơ");
~~~

Trong test thực tế, có thể dùng @GraphQlTest để kiểm tra controller và schema liên quan, mock service để xác minh DTO được bind đúng. Integration test với application context đầy đủ giúp kiểm tra cả runtime wiring, validation và persistence.

Nên kiểm thử các trường hợp:

1. Input hợp lệ được bind vào DTO với đúng giá trị.
2. Input lồng nhau và list được bind đúng cấu trúc.
3. Thiếu field non-null hoặc truyền sai kiểu bị GraphQL từ chối.
4. Enum hoặc custom scalar không hợp lệ bị từ chối.
5. Bean Validation phát hiện chuỗi rỗng, list rỗng hoặc số lượng âm.
6. Business validation từ chối customer, product hoặc tag không hợp lệ.
7. Input update phân biệt omitted và explicit null theo contract.
8. Mutation lỗi không để lại side effect một phần khi use case yêu cầu transaction.
9. Người dùng không có quyền không thể sửa dữ liệu ngoài phạm vi của họ.

Ngoài response, hãy kiểm tra trạng thái dữ liệu sau mutation để xác minh thao tác đã tạo hoặc cập nhật đúng.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không bind được input vào DTO | Tên field hoặc kiểu Java không tương thích SDL | So sánh tên field, constructor và kiểu dữ liệu |
| Dùng object type làm input | Nhầm output type với input object | Khai báo input type riêng |
| Field nullable gây lỗi Java | DTO dùng kiểu nguyên thủy | Dùng kiểu tham chiếu như Integer hoặc Boolean |
| Field lồng nhau không được bind | DTO con không có constructor/property phù hợp | Kiểm tra cấu trúc nested DTO |
| Enum không chuyển đổi được | Giá trị client không khớp enum value | Đồng bộ enum SDL và Java |
| Validation không chạy | Thiếu validation dependency, @Valid hoặc cascade validation | Kiểm tra starter và annotation |
| Update vô tình xóa dữ liệu | Coi omitted và null là cùng một trạng thái | Dùng ArgumentValue khi cần phân biệt |
| Client gửi field nội bộ | Input object quá rộng hoặc bind trực tiếp entity | Tạo DTO theo use case và kiểm tra quyền |
| Mutation tạo dữ liệu dở dang | Transaction đặt sai tầng hoặc xử lý nhiều bước rời rạc | Gom nghiệp vụ nguyên tử vào service có transaction |

## Thực hành tổng hợp

Xây dựng mutation tạo đơn hàng:

1. Khai báo CreateOrderInput với customerId, items, shippingAddress và note.
2. Khai báo CreateOrderItemInput cùng ShippingAddressInput.
3. Tạo Java record tương ứng và controller nhận @Argument("input").
4. Dùng @Valid để kiểm tra dữ liệu cục bộ như recipient không rỗng và quantity dương.
5. Trong OrderService, kiểm tra customer, sản phẩm, tồn kho và quyền truy cập.
6. Đặt transaction tại service nếu tạo order cùng các order item phải nguyên tử.
7. Viết GraphQlTester cho input hợp lệ, thiếu field bắt buộc, list rỗng, quantity âm và product không tồn tại.
8. Thêm UpdateOrderInput với field nullable và dùng ArgumentValue cho field cần phân biệt omitted với null.

Sau khi hoàn thành, hãy giải thích phần nào do GraphQL schema kiểm tra, phần nào do Bean Validation xử lý và phần nào phải do service quyết định.

## Ghi nhớ

Mutation input object gom dữ liệu liên quan vào một cấu trúc có kiểu, giúp schema dễ đọc và dễ mở rộng. Spring for GraphQL dùng @Argument cùng argument binder để chuyển input thành Java record hoặc class, kể cả object lồng nhau, list và enum. GraphQL schema kiểm tra kiểu và nullability; Bean Validation kiểm tra ràng buộc dữ liệu; service kiểm tra quy tắc nghiệp vụ, quyền và transaction. Với update một phần, hãy xác định rõ ý nghĩa của field omitted và explicit null; dùng ArgumentValue<T> khi cần phân biệt hai trạng thái. Kiểm thử mutation bằng variables và GraphQlTester, đồng thời xác minh side effect của thao tác.
