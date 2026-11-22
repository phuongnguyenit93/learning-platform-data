# ID scalar trong GraphQL

`ID` là một scalar type dựng sẵn của GraphQL, dùng để biểu diễn một giá trị định danh. Nó thường xuất hiện ở các field như `id`, `product(id: ...)`, `user(id: ...)` hoặc trong input dùng để tham chiếu tới một đối tượng đã tồn tại.

Điểm quan trọng của `ID` là ý nghĩa định danh và cách serialize: GraphQL trả giá trị `ID` trong response dưới dạng chuỗi. Khi nhận input, GraphQL chấp nhận giá trị chuỗi hoặc số nguyên; tuy nhiên, client thường nên gửi ID dưới dạng chuỗi để giữ định dạng nhất quán. `ID` không phải kiểu số để tính toán và cũng không tự cung cấp cơ chế xác thực hay phân quyền.

## ID là scalar type dựng sẵn

GraphQL định nghĩa năm scalar type dựng sẵn:

| Scalar | Ý nghĩa |
| --- | --- |
| `Int` | Số nguyên có dấu 32-bit. |
| `Float` | Số thực dấu phẩy động. |
| `String` | Chuỗi ký tự UTF-8. |
| `Boolean` | Giá trị đúng hoặc sai. |
| `ID` | Giá trị định danh, được serialize thành chuỗi. |

`ID` là tên kiểu phân biệt chữ hoa chữ thường. Viết đúng `ID`; `Id` hoặc `id` không phải tên của scalar dựng sẵn.

Ví dụ schema:

```graphql
type Product {
  id: ID!
  name: String!
  sku: String!
}

type Query {
  product(id: ID!): Product
  productBySku(sku: String!): Product
}
```

Trong ví dụ này, `id` định danh một Product trong API, còn `sku` là mã sản phẩm theo nghiệp vụ. SKU có thể là chuỗi mà người dùng đọc, tìm kiếm hoặc nhập từ nhãn hàng hóa; ID thường đóng vai trò tham chiếu ổn định tới đối tượng. Hai giá trị có thể trùng định dạng văn bản nhưng mang ý nghĩa khác nhau.

## Quy tắc serialize và input coercion

### Giá trị trả về được serialize thành chuỗi

Khi server trả về một giá trị cho field có kiểu `ID`, GraphQL serialize nó thành biểu diễn chuỗi trong response. Ví dụ một hệ thống lưu khóa chính dạng số nguyên vẫn có thể khai báo field là `ID`:

```graphql
type Product {
  id: ID!
}
```

Response JSON có dạng:

```json
{
  "data": {
    "product": {
      "id": "42"
    }
  }
}
```

Client nhận `"42"` dưới dạng chuỗi, không phải số `42`. Điều này giúp ID không bị hiểu nhầm là một đại lượng để cộng, trừ hoặc sắp xếp theo giá trị số.

### Input chấp nhận chuỗi hoặc số nguyên

Khi dùng `ID` làm đối số hoặc input field, GraphQL chấp nhận giá trị chuỗi và giá trị số nguyên. Ví dụ cả hai dạng literal dưới đây đều hợp lệ về kiểu:

```graphql
query ProductById {
  byString: product(id: "42") {
    id
    name
  }
  byInteger: product(id: 42) {
    id
    name
  }
}
```

Trong ứng dụng client, nên ưu tiên truyền chuỗi:

```graphql
query ProductById($id: ID!) {
  product(id: $id) {
    id
    name
  }
}
```

Variables JSON:

```json
{
  "id": "42"
}
```

Chuỗi giúp giữ nguyên các định danh có số 0 ở đầu, giá trị dài, UUID hoặc mã có ký tự chữ. Ví dụ `"000042"` là một định danh khác với `"42"` nếu hệ thống quy định hai chuỗi đó khác nhau.

GraphQL không chấp nhận mọi loại scalar làm ID input. Giá trị Boolean, Float hoặc object không phải là input hợp lệ cho `ID`. Với field `ID!`, giá trị `null` cũng không hợp lệ; với `ID` nullable, `null` có thể được truyền nếu nghiệp vụ cho phép.

| Input | Hợp lệ cho `ID`? | Ghi chú |
| --- | --- | --- |
| `"42"` | Có | Chuỗi định danh, nên dùng trong variables. |
| `42` | Có | Integer input được chấp nhận và được chuẩn hóa theo quy tắc ID. |
| `42.5` | Không | Float không phải dạng input ID hợp lệ. |
| `true` | Không | Boolean không phải ID. |
| `null` | Tùy nullability | Không hợp lệ với `ID!`. |

## Dùng ID trong Query và Mutation

ID thường được dùng để truy xuất một đối tượng:

```graphql
type Query {
  product(id: ID!): Product
  productsByIds(ids: [ID!]!): [Product!]!
}
```

`product` nhận một ID bắt buộc. `productsByIds` nhận một list ID; cả list và từng phần tử đều không được null. Client có thể gọi:

```graphql
query LoadProducts($ids: [ID!]!) {
  productsByIds(ids: $ids) {
    id
    name
  }
}
```

```json
{
  "ids": ["p-100", "p-101", "p-102"]
}
```

ID cũng thường được dùng trong mutation để xác định đối tượng cần cập nhật hoặc xóa:

```graphql
input UpdateProductInput {
  id: ID!
  name: String
  price: Float
}

type Mutation {
  updateProduct(input: UpdateProductInput!): Product
  deleteProduct(id: ID!): Boolean!
}
```

Việc dùng `ID!` ở input bảo đảm client phải cung cấp một giá trị định danh theo schema. Nó không bảo đảm đối tượng tồn tại trong cơ sở dữ liệu. Service vẫn phải tìm bản ghi, xử lý trường hợp không tìm thấy và áp dụng các quy tắc nghiệp vụ.

## Phân biệt ID với String và Int

Ba scalar có thể cùng mang dữ liệu trông giống nhau nhưng biểu đạt ý nghĩa khác nhau:

| Khai báo | Ý nghĩa phù hợp |
| --- | --- |
| `id: ID!` | Định danh một đối tượng hoặc tài nguyên trong API. |
| `sku: String!` | Mã nghiệp vụ dạng văn bản, có thể tìm kiếm hoặc hiển thị cho người dùng. |
| `quantity: Int!` | Số lượng dùng trong phép tính số học. |

Không nên khai báo `id` là `Int` chỉ vì khóa chính hiện tại của cơ sở dữ liệu là số nguyên. Việc đó khiến client phụ thuộc vào biểu diễn lưu trữ và có thể gây khó khăn nếu sau này chuyển sang UUID hoặc một định dạng định danh khác.

Ngược lại, không phải mọi chuỗi đều nên là `ID`. Tên, email, mã SKU, trạng thái hoặc ghi chú là dữ liệu có ý nghĩa riêng; hãy chọn scalar thể hiện đúng hợp đồng API. Nếu một mã nghiệp vụ cần kiểm tra định dạng đặc biệt, có thể cân nhắc custom scalar hoặc validation ở tầng input/service.

`ID` cũng không quy định cách so sánh, thứ tự hay cấu trúc nội bộ của giá trị. Client nên xem nó như một token định danh và không phân tích nội dung của nó để suy ra thông tin nghiệp vụ.

## Ánh xạ ID trong Spring for GraphQL và Java

Trong Spring for GraphQL, schema SDL vẫn khai báo `ID`; controller nhận đối số bằng `@Argument` như các scalar khác. Một cách đơn giản là dùng `String` trong lớp GraphQL:

```graphql
type Product {
  id: ID!
  name: String!
}

type Query {
  product(id: ID!): Product
}
```

```java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }
}
```

Ở đây GraphQL nhận đối số `id` theo scalar `ID`; phương thức controller nhận giá trị đã được GraphQL xử lý dưới dạng chuỗi. Service có thể chuyển chuỗi sang kiểu định danh nội bộ nếu cần.

### Làm việc với UUID

GraphQL không có scalar `UUID` dựng sẵn. Nếu hệ thống lưu ID bằng `java.util.UUID`, có thể giữ hợp đồng GraphQL là `ID` và chuyển đổi rõ ràng ở ranh giới service:

```java
@QueryMapping
public Product product(@Argument String id) {
    UUID productId;
    try {
        productId = UUID.fromString(id);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException("Product ID không hợp lệ");
    }

    return productService.findById(productId);
}
```

Trong ví dụ thực tế, nên dùng exception và error mapping phù hợp với quy ước API của ứng dụng để trả mã lỗi có thể xử lý ở client. Không nên để thông tin nội bộ hoặc stack trace xuất hiện trong message lỗi công khai.

Khi trả về object có field `id: ID!`, có thể cung cấp giá trị UUID dưới dạng chuỗi bằng `uuid.toString()` hoặc ánh xạ field thành String trong DTO:

```java
public record ProductGraphQlView(
        String id,
        String name) {

    public static ProductGraphQlView from(Product product) {
        return new ProductGraphQlView(
                product.getId().toString(),
                product.getName());
    }
}
```

Cách chuyển đổi tường minh giúp hợp đồng GraphQL độc lập với kiểu khóa chính cụ thể trong persistence. Nếu dự án có cơ chế conversion riêng cho UUID, có thể dùng cơ chế đó, nhưng cần xác minh hành vi coercion và serialization của phiên bản GraphQL Java đang sử dụng.

## ID không tự động bảo vệ tài nguyên

`ID` chỉ mô tả một scalar định danh. Nó không mã hóa quyền truy cập, không xác minh người gọi có quyền xem đối tượng và không ngăn người dùng thử các ID khác.

Ví dụ schema:

```graphql
type Query {
  order(id: ID!): Order
}
```

Việc client biết `orderId` không có nghĩa client được phép đọc đơn hàng đó. Resolver hoặc service cần kiểm tra người dùng hiện tại có quyền truy cập đơn hàng hay không:

```java
@QueryMapping
public Order order(@Argument String id) {
    Order order = orderService.findById(id)
            .orElseThrow(OrderNotFoundException::new);

    authorizationService.checkCanRead(order);
    return order;
}
```

Kiểm tra quyền nên dựa trên principal đã xác thực và phạm vi tài nguyên, bao gồm tenant hoặc chủ sở hữu khi cần. Không dựa vào việc ID khó đoán để thay thế authorization.

### Chọn định dạng ID

Các hệ thống có thể dùng nhiều định dạng:

- **Số tăng dần:** dễ lưu trữ và tra cứu, nhưng có thể để lộ quy mô dữ liệu hoặc hỗ trợ dò tuần tự nếu endpoint không kiểm soát quyền.
- **UUID:** có không gian giá trị lớn và phù hợp với định danh phân tán; cần thống nhất dạng chữ hoa/thường và cách validate.
- **ULID hoặc mã ngẫu nhiên:** có thể hỗ trợ sắp xếp theo thời gian hoặc giảm khả năng đoán tùy cách sinh, nhưng vẫn cần kiểm soát truy cập.
- **Mã nghiệp vụ:** có thể chứa ý nghĩa như tiền tố đơn hàng hoặc mã cửa hàng; cân nhắc liệu có nên công khai cấu trúc đó qua API.

Chọn định dạng theo yêu cầu persistence, tích hợp và vận hành. Nếu cần giảm khả năng dò ID, dùng định danh đủ khó đoán là một lớp hỗ trợ; mọi request vẫn phải qua xác thực và phân quyền.

## ID và mô hình Global Object Identification

Trong một số API theo quy ước Relay, một field `node(id: ID!)` có thể dùng để truy xuất một đối tượng từ global ID:

```graphql
interface Node {
  id: ID!
}

type Product implements Node {
  id: ID!
  name: String!
}

type Query {
  node(id: ID!): Node
}
```

Một triển khai Relay có thể mã hóa loại đối tượng cùng khóa định danh vào global ID, ví dụ một chuỗi Base64 đại diện cho cặp loại và ID. Đây là **quy ước của mô hình Relay hoặc của ứng dụng**, không phải hành vi mặc định của scalar `ID`. GraphQL không tự mã hóa, giải mã hoặc tra cứu object chỉ vì field có kiểu `ID`.

Nếu API không triển khai Global Object Identification, một ID có thể chỉ định danh đối tượng trong một loại tài nguyên cụ thể, chẳng hạn `product(id: ...)` hoặc `order(id: ...)`. Cách diễn giải ID phụ thuộc vào field và hợp đồng của schema.

## Lỗi thường gặp khi sử dụng ID

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Client truyền Float vào đối số `ID` | Nhầm ID với kiểu số. | Gửi chuỗi hoặc integer input theo đúng hợp đồng. |
| ID có số 0 đầu bị thay đổi | Client chuyển ID thành number trước khi gửi. | Giữ ID dưới dạng string từ đầu tới cuối. |
| Resolver nhận kiểu không mong đợi | Binding Java hoặc custom conversion không khớp với scalar coercion. | Kiểm tra giá trị `@Argument`, dùng String ở biên GraphQL và chuyển đổi tường minh. |
| Không tìm thấy đối tượng dù input hợp lệ | Giá trị có kiểu ID đúng nhưng không tồn tại trong hệ thống. | Xử lý not-found ở service và trả lỗi theo quy ước API. |
| Người dùng truy cập được tài nguyên của người khác | Chỉ kiểm tra ID mà không kiểm tra quyền. | Phân quyền theo principal, tenant và tài nguyên. |
| Client giả định ID là số hoặc có thể giải mã | Phụ thuộc vào định dạng nội bộ. | Xem ID là giá trị opaque; chỉ server diễn giải. |

Khi debug, kiểm tra kiểu khai báo trong SDL, kiểu biến trong operation, JSON variables, giá trị controller nhận được và bước chuyển đổi sang định danh persistence. Đồng thời xác minh quyền truy cập ở service.

## Ghi nhớ

`ID` là scalar dựng sẵn của GraphQL dành cho giá trị định danh. Server serialize ID thành chuỗi; input coercion chấp nhận chuỗi hoặc số nguyên. Nên truyền ID bằng chuỗi để giữ nguyên định dạng và xem ID như một giá trị opaque, không dùng nó cho phép tính số học.

Trong Spring for GraphQL, có thể nhận ID bằng `@Argument String` rồi chuyển đổi sang UUID hoặc kiểu khóa nội bộ ở tầng service. `ID` không tự bảo đảm tính duy nhất toàn hệ thống, không xác minh đối tượng tồn tại và không cấp quyền truy cập. Xác thực và phân quyền vẫn phải được thực hiện độc lập cho từng tài nguyên.
