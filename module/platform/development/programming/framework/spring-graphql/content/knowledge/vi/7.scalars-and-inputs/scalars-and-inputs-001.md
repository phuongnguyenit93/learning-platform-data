# String, Int, Float và Boolean trong GraphQL

GraphQL cung cấp bốn scalar cơ bản thường xuất hiện trong hầu hết API: `String`, `Int`, `Float` và `Boolean`. Scalar là kiểu dữ liệu đơn, không có các field con để client chọn tiếp. Chúng được dùng trực tiếp trong output object, argument của field và input object.

Trong Spring for GraphQL, các scalar chuẩn này đã được GraphQL hỗ trợ sẵn. Ta khai báo chúng trong SDL, sau đó ánh xạ giá trị sang kiểu Java phù hợp trong resolver hoặc input object. Điều quan trọng là hiểu kiểu dữ liệu, giới hạn và quy tắc chuyển đổi ở cả hai chiều: dữ liệu client gửi vào và kết quả server trả về.

## 1. Tổng quan bốn scalar cơ bản

| Scalar GraphQL | Ý nghĩa | Kiểu Java thường dùng | Kiểu JSON tương ứng |
| --- | --- | --- | --- |
| `String` | Văn bản Unicode | `String` | String |
| `Int` | Số nguyên có dấu 32-bit | `Integer` / `int` | Number nguyên |
| `Float` | Số thực dấu phẩy động độ chính xác kép | `Double` / `double` | Number |
| `Boolean` | Giá trị đúng hoặc sai | `Boolean` / `boolean` | Boolean |

Các scalar trên mặc định là nullable. Thêm `!` để yêu cầu giá trị khác null, ví dụ `String!`, `Int!`, `Float!` hoặc `Boolean!`. Nullability là quy tắc riêng của GraphQL; nó không tự suy ra từ việc một thuộc tính Java dùng kiểu primitive hay wrapper.

## 2. String: dữ liệu văn bản

`String` biểu diễn chuỗi ký tự. GraphQL SDL dùng dấu nháy kép cho string literal:

```graphql
type Query {
    greeting(name: String!): String!
    description: String
}
```

Client có thể gọi query:

```graphql
query {
    greeting(name: "An")
    description
}
```

Response mẫu:

```json
{
  "data": {
    "greeting": "Xin chào, An!",
    "description": null
  }
}
```

Một số quy tắc cần nhớ:

- String literal dùng dấu nháy kép, ví dụ `"GraphQL"`; cú pháp dấu nháy đơn như `'GraphQL'` không phải string literal hợp lệ trong GraphQL.
- Chuỗi có thể chứa Unicode, nên tiếng Việt có dấu được hỗ trợ bình thường.
- Khi cần biểu diễn dấu nháy kép, dấu gạch chéo ngược hoặc xuống dòng trong literal, phải escape theo cú pháp GraphQL string.
- `String!` không có nghĩa chuỗi phải khác rỗng. Chuỗi `""` vẫn là một String khác null; quy tắc không rỗng cần được kiểm tra ở tầng nghiệp vụ.

Ví dụ một input object nhận thông tin tìm kiếm:

```graphql
input ProductSearchInput {
    keyword: String
    category: String
}

type Query {
    searchProducts(filter: ProductSearchInput!): [Product!]!
}
```

`keyword` và `category` đều nullable, do đó client có thể bỏ qua hoặc gửi null theo hợp đồng input. Nếu ứng dụng cần phân biệt bỏ qua với truyền null, hãy dùng cơ chế binding phù hợp của Spring for GraphQL và xác định rõ hành vi cập nhật/tìm kiếm.

Resolver Java nên trả về `String` cho field String:

```java
@QueryMapping
public String greeting(@Argument("name") String name) {
    return "Xin chào, " + name + "!";
}
```

Không nên trả một object domain tùy ý cho field `String` và trông chờ GraphQL tự chọn thuộc tính cần serialize. Hãy trả đúng kiểu dữ liệu mà schema công bố hoặc ánh xạ object thành chuỗi rõ ràng ở tầng ứng dụng.

## 3. Int: số nguyên 32-bit có dấu

GraphQL `Int` là số nguyên có dấu 32-bit. Giá trị hợp lệ nằm trong khoảng:

\[
-2^{31} \leq n \leq 2^{31}-1
\]

Tương đương từ `-2147483648` đến `2147483647`. `Int` phù hợp với số lượng, thứ tự, số trang hoặc số lần đếm trong phạm vi này.

Ví dụ schema:

```graphql
type Product {
    stock: Int!
    reviewCount: Int!
}

type Query {
    totalProducts: Int!
    productsInStock(minimum: Int = 1): [Product!]!
}
```

Một query:

```graphql
query {
    totalProducts
    productsInStock(minimum: 5) {
        stock
        reviewCount
    }
}
```

`Int` nhận số nguyên, không nhận giá trị thập phân. Ví dụ `5` hợp lệ, còn `5.5` không phải giá trị Int hợp lệ. Giá trị vượt quá phạm vi 32-bit cũng bị từ chối khi input hoặc không thể serialize thành Int ở output.

Trong Java, dùng `Integer` hoặc `int` để ánh xạ GraphQL `Int`. Nếu field nullable hoặc input có thể bị bỏ qua, ưu tiên `Integer` vì kiểu wrapper có thể biểu diễn null. Kiểu primitive `int` luôn có giá trị số và không thể biểu diễn null; biến primitive chưa được gán còn có thể mang giá trị mặc định `0`, khiến ứng dụng khó phân biệt client đã gửi số 0 hay chưa gửi giá trị.

Ví dụ resolver:

```java
@QueryMapping
public Integer totalProducts() {
    return productService.countProducts();
}
```

Nếu hệ thống cần số nguyên lớn hơn giới hạn 32-bit, không nên cố ép dữ liệu vào `Int`. Hãy cân nhắc thiết kế scalar riêng hoặc biểu diễn giá trị bằng `String` với quy tắc định dạng rõ ràng. GraphQL built-in `Int` không phải kiểu `long` 64-bit.

## 4. Float: số thực độ chính xác kép

GraphQL `Float` biểu diễn số thực dấu phẩy động độ chính xác kép. Trong Java, kiểu thường dùng là `Double` hoặc `double`.

```graphql
type Product {
    rating: Float
    averagePrice: Float!
}

type Query {
    averageRating: Float
}
```

Float literal có thể dùng phần thập phân hoặc số mũ:

```graphql
query {
    averageRating
}
```

Ví dụ giá trị response:

```json
{
  "data": {
    "averageRating": 4.75
  }
}
```

GraphQL `Float` nhận giá trị số nguyên hoặc số thực ở vị trí input Float. Vì vậy, `4`, `4.0` và `4.75` đều có thể được coercion thành Float. Một chuỗi như `"4.75"` không phải giá trị số Float hợp lệ. Giá trị không hữu hạn như `NaN` hoặc vô cực không phải số JSON hợp lệ để truyền qua GraphQL response.

Ví dụ resolver:

```java
@QueryMapping
public Double averageRating() {
    return productService.calculateAverageRating();
}
```

Không nên dùng GraphQL `Float` để lưu hoặc truyền tiền tệ cần độ chính xác thập phân tuyệt đối. Số dấu phẩy động nhị phân có thể biểu diễn một số thập phân gần đúng, dẫn đến sai số khi tính toán. Với tiền, thường nên dùng số nguyên theo đơn vị nhỏ nhất (ví dụ số cent) hoặc custom scalar dựa trên `BigDecimal` với quy tắc serialize/parse được định nghĩa rõ ràng.

## 5. Boolean: giá trị đúng hoặc sai

GraphQL `Boolean` chỉ biểu diễn hai giá trị `true` và `false`. Literal Boolean dùng chữ thường:

```graphql
type Product {
    active: Boolean!
    featured: Boolean
}

type Query {
    isStoreOpen: Boolean!
}
```

Ví dụ query:

```graphql
query {
    isStoreOpen
    products {
        active
        featured
    }
}
```

Ví dụ response:

```json
{
  "data": {
    "isStoreOpen": true,
    "products": [
      { "active": true, "featured": false },
      { "active": true, "featured": null }
    ]
  }
}
```

`Boolean` không tự chuyển các chuỗi như `"true"`, `"yes"` hoặc số `1` thành Boolean trong input. Client cần gửi đúng kiểu JSON boolean. `Boolean!` yêu cầu một giá trị true hoặc false; nó không chấp nhận null.

Trong Java, dùng `Boolean` cho field nullable và `boolean` khi hợp đồng luôn có giá trị. Với input tùy chọn, wrapper `Boolean` giúp phân biệt `null` với `false`. Nếu dùng primitive `boolean`, giá trị mặc định là `false`, nên trạng thái client không gửi field có thể bị nhập nhằng với client chủ động gửi false.

## 6. Kết hợp các scalar trong một schema

Một schema thực tế có thể dùng cả bốn scalar trong cùng object và input:

```graphql
type Product {
    id: ID!
    name: String!
    stock: Int!
    rating: Float
    active: Boolean!
}

input ProductFilter {
    keyword: String
    minimumStock: Int
    minimumRating: Float
    activeOnly: Boolean = true
}

type Query {
    products(filter: ProductFilter!): [Product!]!
}
```

Trong ví dụ này:

- `name` là văn bản bắt buộc.
- `stock` là số nguyên 32-bit và không được null.
- `rating` là số thực nullable vì sản phẩm có thể chưa được đánh giá.
- `active` luôn có trạng thái true hoặc false.
- `keyword`, `minimumStock` và `minimumRating` là các điều kiện lọc tùy chọn.
- `activeOnly` mặc định là true nếu client không cung cấp field này.

Client có thể gửi query và variables:

```graphql
query FindProducts($filter: ProductFilter!) {
    products(filter: $filter) {
        id
        name
        stock
        rating
        active
    }
}
```

```json
{
  "filter": {
    "keyword": "keyboard",
    "minimumStock": 3,
    "minimumRating": 4.25,
    "activeOnly": true
  }
}
```

Variables JSON phải giữ đúng kiểu scalar: chuỗi đặt trong dấu nháy kép, số nguyên không có phần thập phân cho `Int`, số cho `Float`, và `true`/`false` cho `Boolean`. Không gửi tất cả giá trị dưới dạng string rồi kỳ vọng GraphQL tự chuyển đổi.

## 7. Ánh xạ input object sang Java

Với Spring for GraphQL, input object có thể được bind vào Java record hoặc class. Ví dụ:

```java
public record ProductFilter(
        String keyword,
        Integer minimumStock,
        Double minimumRating,
        Boolean activeOnly) {
}
```

Resolver nhận input object bằng `@Argument`:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public List<Product> products(@Argument("filter") ProductFilter filter) {
        return productService.search(filter);
    }
}
```

`String`, `Integer`, `Double` và `Boolean` lần lượt tương ứng với bốn scalar trong SDL. Các wrapper được dùng trong record vì những field input này có thể bị bỏ qua hoặc nhận null. Nếu SDL cung cấp default như `activeOnly: Boolean = true`, GraphQL áp dụng default khi field bị bỏ qua; hãy kiểm tra cách binding của input object và dùng giá trị nhận được theo hợp đồng đã khai báo.

Nếu cần phân biệt field bị bỏ qua với field được truyền null, có thể dùng `ArgumentValue<T>` ở argument phù hợp hoặc một kiểu binding hỗ trợ giữ trạng thái hiện diện của input. Không nên dùng primitive cho field tùy chọn vì primitive làm mất thông tin null/omitted.

## 8. Validation: scalar đúng kiểu chưa chắc đúng nghiệp vụ

GraphQL scalar kiểm tra kiểu và khả năng chuyển đổi cơ bản. Chúng không thay thế validation nghiệp vụ. Ví dụ:

- `name: String!` vẫn có thể nhận chuỗi rỗng.
- `age: Int!` vẫn có thể nhận số âm nếu schema không có quy tắc bổ sung.
- `rating: Float` vẫn có thể nhận giá trị `-100.0` dù nghiệp vụ chỉ cho phép từ 0 đến 5.
- `active: Boolean!` chỉ xác nhận true/false, không quyết định ai có quyền thay đổi trạng thái.

Có thể kiểm tra các điều kiện này trong service hoặc tầng validation của ứng dụng. Ví dụ:

```java
public ProductFilter validate(ProductFilter filter) {
    if (filter.minimumStock() != null && filter.minimumStock() < 0) {
        throw new IllegalArgumentException("minimumStock không được âm");
    }

    if (filter.minimumRating() != null
            && (filter.minimumRating() < 0 || filter.minimumRating() > 5)) {
        throw new IllegalArgumentException("minimumRating phải nằm trong khoảng 0 đến 5");
    }

    if (filter.keyword() != null && filter.keyword().isBlank()) {
        throw new IllegalArgumentException("keyword không được chỉ chứa khoảng trắng");
    }

    return filter;
}
```

Đoạn code chỉ minh họa validation đầu vào; ứng dụng thực tế nên ánh xạ lỗi validation thành GraphQL error có thông tin phù hợp cho client. Tránh trả stack trace hoặc chi tiết nội bộ trong message.

## 9. Literal và variables: gửi đúng kiểu dữ liệu

GraphQL hỗ trợ truyền giá trị trực tiếp trong document hoặc dùng variables. Với document:

```graphql
query {
    productByCode(code: "P-100") {
        name
    }
    productsWithStock(minimum: 10) {
        name
    }
}
```

Với variables, document khai báo kiểu biến và request body cung cấp giá trị JSON:

```graphql
query ProductByCode($code: String!, $minimum: Int!) {
    productByCode(code: $code) {
        name
    }
    productsWithStock(minimum: $minimum) {
        name
    }
}
```

```json
{
  "code": "P-100",
  "minimum": 10
}
```

Variables hữu ích vì client có thể tái sử dụng GraphQL document và thay đổi dữ liệu đầu vào mà không cần ghép chuỗi query. Chúng cũng giúp tránh lỗi escape string và làm rõ kiểu của từng giá trị.

Ví dụ gọi HTTP endpoint bằng `curl`:

```bash
curl http://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "query": "query ProductByCode($code: String!, $minimum: Int!) { productByCode(code: $code) { name } productsWithStock(minimum: $minimum) { name } }",
    "variables": { "code": "P-100", "minimum": 10 },
    "operationName": "ProductByCode"
  }'
```

## 10. Kiểm thử scalar với GraphQlTester

Kiểm thử nên xác nhận scalar được bind vào Java và serialize ra response đúng kiểu. Ví dụ với `GraphQlTester` đã được cấu hình trong test context:

```java
@Test
void scalarArgumentsAreMappedToExpectedValues() {
    graphQlTester.document("""
            query Greeting($name: String!, $count: Int!, $ratio: Float!, $enabled: Boolean!) {
                greeting(name: $name)
                repeatedCount(count: $count)
                scaledValue(ratio: $ratio)
                enabled(value: $enabled)
            }
            """)
        .variable("name", "An")
        .variable("count", 3)
        .variable("ratio", 2.5)
        .variable("enabled", true)
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Xin chào, An!");
}
```

Các field `repeatedCount`, `scaledValue` và `enabled` trong ví dụ cần được khai báo trong schema và có resolver tương ứng. Có thể viết assertion riêng cho từng field bằng `.path(...).entity(Integer.class)`, `.entity(Double.class)` hoặc `.entity(Boolean.class)` để xác nhận kiểu và giá trị trả về.

Nên bổ sung các trường hợp biên:

1. String có dấu tiếng Việt, ký tự đặc biệt và chuỗi rỗng.
2. Int ở giá trị biên 32-bit và giá trị vượt giới hạn.
3. Int nhận literal thập phân hoặc biến JSON không phải số nguyên.
4. Float nhận số nguyên, số thập phân và từ chối chuỗi số.
5. Boolean nhận true/false và từ chối string hoặc number.
6. Scalar nullable nhận null; scalar Non-Null từ chối null.
7. Input object áp dụng default khi field bị bỏ qua.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| String argument bị từ chối | Client gửi number hoặc boolean thay cho string | Gửi JSON string hoặc GraphQL string literal. |
| Int bị từ chối dù giá trị trông giống số | Giá trị có phần thập phân hoặc vượt giới hạn 32-bit | Gửi integer trong phạm vi hợp lệ; dùng scalar khác nếu domain cần số lớn. |
| Float không nhận giá trị | Client gửi string thay vì JSON number, hoặc giá trị không hữu hạn | Gửi số JSON hữu hạn. |
| Boolean không nhận `"true"` | Đây là string, không phải Boolean | Gửi `true` hoặc `false` không có dấu nháy. |
| Resolver vi phạm Non-Null | Resolver trả null trong khi SDL khai báo `!` | Bảo đảm luôn có giá trị hoặc điều chỉnh nullability đúng nghiệp vụ. |
| Số tiền có sai số | Dùng Float cho phép tính thập phân cần độ chính xác tuyệt đối | Dùng đơn vị tiền nhỏ nhất dạng Int hoặc custom scalar dựa trên BigDecimal. |
| Input tùy chọn bị biến thành 0/false | Dùng primitive Java cho dữ liệu có thể bị bỏ qua | Dùng wrapper `Integer`, `Double`, `Boolean` hoặc binding giữ trạng thái omitted. |

## 12. Checklist khi dùng scalar cơ bản

1. Chọn `String` cho văn bản, `Int` cho số nguyên 32-bit, `Float` cho số thực độ chính xác kép và `Boolean` cho trạng thái đúng/sai.
2. Thêm `!` chỉ khi ứng dụng có thể bảo đảm giá trị khác null.
3. Dùng đúng kiểu JSON khi gửi variables; không mã hóa mọi giá trị thành string.
4. Ánh xạ sang `String`, `Integer`, `Double` và `Boolean` trong Java.
5. Ưu tiên wrapper cho field nullable hoặc input tùy chọn để giữ được null.
6. Kiểm tra giới hạn 32-bit của Int và sai số dấu phẩy động của Float.
7. Dùng validation nghiệp vụ cho miền giá trị, chuỗi rỗng, số âm hoặc giới hạn rating.
8. Không dùng Float cho tiền tệ cần độ chính xác tuyệt đối.
9. Kiểm thử input, output, nullability và các giá trị biên.

Bốn scalar `String`, `Int`, `Float` và `Boolean` tạo nên nền tảng kiểu dữ liệu cho phần lớn schema GraphQL. Khi khai báo đúng hợp đồng trong SDL, gửi variables đúng kiểu và ánh xạ sang Java phù hợp, API sẽ dễ dùng hơn và tránh được nhiều lỗi coercion khi chạy thực tế.
