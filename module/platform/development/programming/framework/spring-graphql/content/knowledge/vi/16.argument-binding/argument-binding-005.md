# Binding scalar argument trong Spring for GraphQL

Trong GraphQL, field có thể khai báo argument với kiểu scalar như `ID`, `String`, `Int`, `Float` hoặc `Boolean`. Ở phía Spring for GraphQL, annotation `@Argument` giúp lấy giá trị đó từ operation và bind vào tham số của phương thức controller.

Ví dụ field `product(id: ID!): Product` yêu cầu client truyền một ID. Phương thức `@QueryMapping` có thể nhận ID bằng tham số Java `String`:

```graphql
type Query {
  product(id: ID!): Product
}
```

```java
@QueryMapping
public Product product(@Argument("id") String productId) {
    return productService.findById(productId).orElse(null);
}
```

GraphQL kiểm tra kiểu và coercion của argument theo schema trước khi gọi resolver. Spring for GraphQL sau đó cung cấp giá trị cho tham số được đánh dấu `@Argument`. Vì vậy, cần thống nhất ba phần: tên argument trong SDL, tên được chỉ định trong annotation và kiểu Java mà phương thức nhận.

## Scalar argument trong GraphQL SDL

GraphQL có năm scalar type dựng sẵn:

| Scalar | Ý nghĩa | Kiểu Java thường dùng |
| --- | --- | --- |
| `Int` | Số nguyên có dấu 32-bit. | `Integer` |
| `Float` | Số thực dấu phẩy động độ chính xác kép. | `Double` |
| `String` | Chuỗi ký tự. | `String` |
| `Boolean` | Giá trị đúng hoặc sai. | `Boolean` |
| `ID` | Giá trị định danh, được serialize thành chuỗi. | `String` |

Ví dụ schema khai báo nhiều scalar argument:

```graphql
type Query {
  product(id: ID!): Product
  searchProducts(keyword: String!, minPrice: Float, limit: Int = 20): [Product!]!
  products(activeOnly: Boolean = true): [Product!]!
}
```

Các dấu `!` và giá trị mặc định quyết định argument có thể bị bỏ qua hoặc nhận `null` hay không. `keyword: String!` bắt buộc phải có giá trị khác null; `minPrice: Float` có thể không được truyền hoặc được truyền `null`; `limit` có giá trị mặc định là `20` khi argument bị bỏ qua.

`ID` phù hợp với định danh, không phải số để tính toán. Dù khóa chính hiện tại trong database là số nguyên, thường nên nhận ID ở Java dưới dạng `String` để không gắn hợp đồng API với kiểu lưu trữ.

## Dùng `@Argument` trong annotated controller

Spring for GraphQL dùng `@Argument` để đánh dấu tham số nhận argument của field đang được xử lý. Có thể khai báo tên argument trực tiếp:

```java
@Controller
public class ProductQueryController {

    private final ProductService productService;

    public ProductQueryController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument("id") String productId) {
        return productService.findById(productId).orElse(null);
    }
}
```

Trong ví dụ, tên tham số Java là `productId`, còn tên argument SDL là `id`. `@Argument("id")` nói rõ Spring cần bind giá trị từ argument `id` vào tham số `productId`.

Nếu tên tham số Java trùng với tên argument, có thể dùng dạng ngắn:

```java
@QueryMapping
public Product product(@Argument String id) {
    return productService.findById(id).orElse(null);
}
```

Khi dựa vào tên tham số Java, cần bảo đảm quá trình build giữ metadata tên tham số, chẳng hạn bật tùy chọn biên dịch `-parameters` nếu cấu hình dự án yêu cầu. Dùng tên tường minh trong `@Argument("...")` giúp mapping ổn định hơn khi đổi tên biến hoặc cấu hình build.

`@Argument` dùng được với field trên Query, Mutation và field lồng nhau được xử lý bằng `@SchemaMapping`. Giá trị argument luôn thuộc field hiện tại, không phải argument của field cha.

## Bind nhiều scalar argument

Một field có thể nhận nhiều scalar argument. Spring bind từng argument vào tham số tương ứng:

```graphql
type Query {
  searchProducts(
    keyword: String!
    minPrice: Float
    maxPrice: Float
    limit: Int = 20
    activeOnly: Boolean = true
  ): [Product!]!
}
```

```java
@QueryMapping
public List<Product> searchProducts(
        @Argument("keyword") String keyword,
        @Argument("minPrice") Double minPrice,
        @Argument("maxPrice") Double maxPrice,
        @Argument("limit") Integer limit,
        @Argument("activeOnly") Boolean activeOnly) {
    return productService.search(
            keyword, minPrice, maxPrice, limit, activeOnly);
}
```

Các kiểu wrapper `Integer`, `Double` và `Boolean` có thể biểu diễn `null`. Nếu argument được khai báo nullable, dùng kiểu wrapper sẽ an toàn hơn kiểu primitive như `int`, `double` hoặc `boolean`, vì primitive Java không thể chứa null.

Trong ví dụ này, SDL cung cấp mặc định cho `limit` và `activeOnly`. Khi client bỏ qua hai argument đó, GraphQL áp dụng giá trị mặc định trước khi gọi resolver. Vì vậy, controller nhận giá trị đã được áp dụng default theo schema.

## Truyền argument bằng variables

Client có thể truyền scalar trực tiếp trong operation, nhưng với ứng dụng thực tế nên ưu tiên variables. Variables tách dữ liệu đầu vào khỏi nội dung query, giúp tái sử dụng operation và tránh nối chuỗi thủ công.

```graphql
query SearchProducts(
  $keyword: String!
  $minPrice: Float
  $limit: Int = 20
) {
  searchProducts(
    keyword: $keyword
    minPrice: $minPrice
    limit: $limit
  ) {
    id
    name
    price
  }
}
```

Variables JSON:

```json
{
  "keyword": "keyboard",
  "minPrice": 500000,
  "limit": 10
}
```

Kiểu khai báo của variable phải tương thích với vị trí argument trong schema. Ví dụ `$keyword: String!` có thể truyền vào `keyword: String!`; một variable nullable `String` không thể dùng ở vị trí bắt buộc `String!` nếu không có default phù hợp theo quy tắc GraphQL.

Không ghép trực tiếp giá trị client vào query bằng string concatenation. Dùng variables giúp GraphQL kiểm tra kiểu input và tránh lỗi cú pháp do dữ liệu chứa dấu nháy hoặc ký tự đặc biệt.

## GraphQL coercion diễn ra trước khi gọi resolver

Khi nhận operation, GraphQL kiểm tra và chuyển đổi giá trị input theo kiểu khai báo. Với scalar argument, hai trường hợp quan trọng là:

- **Inline literal:** giá trị nằm trực tiếp trong query, ví dụ `product(id: "p-100")`. GraphQL kiểm tra literal theo scalar type.
- **Variable:** giá trị nằm trong phần variables JSON, ví dụ `{ "id": "p-100" }`. GraphQL kiểm tra và coercion giá trị runtime theo kiểu variable.

Nếu client truyền sai kiểu, GraphQL báo lỗi validation hoặc input coercion trước khi gọi DataFetcher. Ví dụ `limit: "ten"` không hợp lệ khi schema yêu cầu `Int`; resolver không nên phải tự phân tích chuỗi đó.

Một số lưu ý theo scalar:

- `Int` chỉ biểu diễn số nguyên trong phạm vi signed 32-bit. Giá trị vượt phạm vi cần kiểu scalar khác.
- `Float` biểu diễn số thực độ chính xác kép; không nên dùng nó cho tiền tệ cần phép toán thập phân chính xác.
- `Boolean` chỉ nhận giá trị boolean, không tự chuyển chuỗi `"true"` thành `true` theo quy tắc GraphQL.
- `String` nhận chuỗi, không tự chuyển mọi kiểu JSON thành văn bản.
- `ID` được serialize thành chuỗi và input coercion hỗ trợ dạng chuỗi hoặc số nguyên. Trong client, nên gửi ID dưới dạng chuỗi để giữ định dạng như số 0 ở đầu.

GraphQL coercion kiểm tra kiểu dữ liệu, không thay thế validation nghiệp vụ. Ví dụ `minPrice: -10` vẫn là một giá trị Float hợp lệ về mặt GraphQL; service cần kiểm tra giá không âm nếu nghiệp vụ yêu cầu.

## Nullable, Non-Null và giá trị mặc định

Khi bind argument, cần phân biệt ba trường hợp: argument bị bỏ qua, argument được truyền với `null`, và argument được truyền với một giá trị.

| SDL | Bỏ qua argument | Truyền `null` |
| --- | --- | --- |
| `name: String` | Hợp lệ; giá trị có thể không có. | Hợp lệ. |
| `name: String!` | Không hợp lệ nếu không có default. | Không hợp lệ. |
| `limit: Int = 20` | Hợp lệ; dùng `20`. | Hợp lệ về kiểu nullable; giá trị explicit null không bị thay bằng `20`. |
| `limit: Int! = 20` | Hợp lệ; dùng `20`. | Không hợp lệ. |

Default được áp dụng khi argument bị bỏ qua. Nếu client truyền rõ `null` vào một argument nullable, giá trị vẫn là null; default không thay thế explicit null.

Với tham số Java nullable thông thường, giá trị bị bỏ qua và giá trị explicit null có thể cùng được biểu diễn thành `null`. Nếu nghiệp vụ cần phân biệt hai trạng thái này, có thể dùng `ArgumentValue<T>`:

```java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public List<Product> products(
        @Argument("category") ArgumentValue<String> category) {
    if (category.isOmitted()) {
        return productService.findAllCategories();
    }

    if (category.value() == null) {
        return productService.findWithoutCategory();
    }

    return productService.findByCategory(category.value());
}
```

Đoạn code giả định `category` được khai báo nullable trong SDL. `ArgumentValue` cho biết argument có bị bỏ qua hay không; `value()` chứa giá trị được truyền, có thể là null. Nếu schema khai báo `category: String!`, GraphQL đã từ chối trường hợp bỏ qua hoặc null trước khi controller chạy.

## Binding vào kiểu Java phù hợp

Chọn kiểu Java dựa trên scalar và nullability:

```graphql
type Query {
  product(id: ID!): Product
  products(limit: Int, minPrice: Float, active: Boolean): [Product!]!
}
```

```java
@QueryMapping
public Product product(@Argument("id") String id) {
    return productService.findById(id).orElse(null);
}

@QueryMapping
public List<Product> products(
        @Argument("limit") Integer limit,
        @Argument("minPrice") Double minPrice,
        @Argument("active") Boolean active) {
    return productService.search(limit, minPrice, active);
}
```

Không nên bind GraphQL `Int` sang Java `Long` với giả định GraphQL tự hỗ trợ số nguyên 64-bit. `Int` của GraphQL vẫn là signed 32-bit; nếu nghiệp vụ cần số nguyên lớn, hãy định nghĩa custom scalar với quy tắc coercion rõ ràng.

Với tiền tệ, `Float` có thể gây sai số dấu phẩy động. Có thể dùng custom scalar như `Decimal` hoặc biểu diễn amount bằng đơn vị nhỏ nhất (ví dụ số xu) tùy hợp đồng API. Custom scalar cần định nghĩa coercion ở GraphQL Java và kiểu Java tương ứng.

## Custom scalar argument

Khi một giá trị không phù hợp với năm scalar dựng sẵn, schema có thể khai báo custom scalar. Ví dụ `DateTime` biểu diễn thời điểm:

```graphql
scalar DateTime

type Query {
  eventsSince(from: DateTime!): [Event!]!
}
```

Để bind thành `Instant`, ứng dụng cần đăng ký `GraphQLScalarType` có `Coercing` xác định cách đọc input literal, parse variable và serialize output. `Coercing` phải kiểm tra định dạng, múi giờ và giá trị hợp lệ; sau đó resolver có thể nhận kiểu Java tương ứng:

```java
@QueryMapping
public List<Event> eventsSince(@Argument("from") Instant from) {
    return eventService.findSince(from);
}
```

Đoạn controller chỉ hoạt động khi custom scalar `DateTime` đã được đăng ký và coercion trả về `Instant` tương thích. Nếu scalar chỉ parse thành `String`, tham số `Instant` cần một conversion phù hợp hoặc resolver nhận `String` rồi chuyển đổi tường minh.

Trong Spring for GraphQL, có thể đăng ký custom scalar qua `RuntimeWiringConfigurer` hoặc cơ chế bean/runtime wiring tương ứng của phiên bản Spring Boot đang dùng. Cần kiểm tra cả input variables lẫn output serialization bằng test tích hợp.

## Binding scalar argument ở field lồng nhau

Argument không chỉ xuất hiện trên Query root. Một field của object type cũng có thể nhận scalar argument:

```graphql
type Book {
  id: ID!
  title: String!
  summary(maxLength: Int = 200): String
}
```

```java
@SchemaMapping(typeName = "Book", field = "summary")
public String summary(Book book, @Argument("maxLength") Integer maxLength) {
    return summaryService.createSummary(book.getId(), maxLength);
}
```

Ở đây `Book book` là source object do field cha cung cấp; `maxLength` là argument của field `Book.summary`. Spring bind hai nguồn dữ liệu riêng biệt vào method parameters.

Điều này cũng áp dụng cho `@MutationMapping` và `@SubscriptionMapping`: `@Argument` luôn lấy argument của field mà method đang xử lý.

## Validation sau khi bind

GraphQL schema kiểm tra cấu trúc và kiểu scalar, nhưng không biết mọi quy tắc nghiệp vụ. Sau khi bind, service hoặc lớp validation cần kiểm tra những điều kiện như:

- `limit` phải nằm trong giới hạn cho phép, ví dụ từ 1 đến 100.
- `minPrice` không được âm.
- `keyword` không được chỉ chứa khoảng trắng.
- ID phải trỏ tới tài nguyên tồn tại và người dùng có quyền truy cập.
- `from` không được nằm sau `to` trong truy vấn khoảng thời gian.

Có thể dùng Bean Validation hoặc validation trong service tùy cấu trúc ứng dụng. Dù chọn cách nào, lỗi validation nên được chuyển thành GraphQL error có message và mã lỗi ổn định. Không dựa vào GraphQL scalar coercion để thay thế validation nghiệp vụ.

## Kiểm thử scalar argument binding

`GraphQlTester` có thể gửi operation cùng variables để xác minh giá trị được bind vào controller và response được tạo đúng:

```java
@Test
void bindsScalarVariables() {
    graphQlTester.document("""
        query Search($keyword: String!, $limit: Int) {
          searchProducts(keyword: $keyword, limit: $limit) {
            id
            name
          }
        }
        """)
        .variable("keyword", "keyboard")
        .variable("limit", 5)
        .execute()
        .path("searchProducts[0].name")
        .entity(String.class)
        .isEqualTo("Mechanical Keyboard");
}
```

Ngoài trường hợp thành công, nên kiểm tra:

- Argument có tên khác với tham số Java nhưng được chỉ rõ bằng `@Argument("...")`.
- Variable thiếu đối với argument Non-Null bị từ chối trước khi resolver chạy.
- Sai scalar type, chẳng hạn chuỗi truyền vào `Int`, tạo lỗi coercion.
- `Int` vượt giới hạn 32-bit bị từ chối.
- Nullable argument nhận `null` đúng như hợp đồng.
- Argument bị bỏ qua dùng default SDL.
- Explicit null không bị thay bằng default.
- `ArgumentValue` phân biệt omitted và explicit null nếu nghiệp vụ cần.
- Custom scalar parse variables, parse literals và serialize output đúng.
- Validation nghiệp vụ từ chối giá trị có kiểu đúng nhưng không hợp lệ.

Khi kiểm tra resolver không được gọi trong trường hợp coercion thất bại, có thể dùng mock service và xác minh không có tương tác. Điều này xác nhận lỗi được phát hiện ở GraphQL layer trước khi chạy nghiệp vụ.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@Argument` nhận null dù client gửi giá trị | Tên argument SDL không khớp annotation hoặc variable không được truyền đúng. | Kiểm tra tên trong SDL, `@Argument("...")` và variables. |
| Spring không bind được tham số | Kiểu Java không tương thích với giá trị scalar sau coercion. | Dùng kiểu Java phù hợp hoặc đăng ký conversion/custom scalar rõ ràng. |
| Argument bắt buộc bị bỏ qua | SDL khai báo Non-Null và không có default. | Truyền variable hoặc khai báo default nếu nghiệp vụ cho phép. |
| Giá trị mặc định không được áp dụng | Client truyền explicit `null`; default chỉ áp dụng khi bị bỏ qua. | Phân biệt omitted với null và điều chỉnh schema/logic. |
| `Int` không nhận số lớn | GraphQL `Int` chỉ là signed 32-bit. | Dùng custom scalar cho số nguyên lớn. |
| Số tiền bị sai số | Dùng `Float` cho phép tính thập phân chính xác. | Dùng decimal custom scalar hoặc đơn vị tiền nhỏ nhất. |
| Primitive Java gây lỗi khi argument null | `int`, `double`, `boolean` không thể chứa null. | Dùng wrapper `Integer`, `Double`, `Boolean` cho argument nullable. |
| Custom scalar không bind được thành `Instant` | `Coercing` trả về kiểu khác hoặc chưa được đăng ký. | Đồng bộ kiểu parseValue với kiểu tham số và kiểm thử runtime wiring. |

## Ghi nhớ

`@Argument` lấy giá trị từ argument của field hiện tại và bind vào tham số phương thức controller. Tên trong SDL phải khớp với tên annotation; nên chỉ rõ `@Argument("name")` khi cần mapping ổn định. Dùng kiểu Java tương ứng với scalar, ưu tiên wrapper cho argument nullable và nhớ rằng GraphQL `Int` là số nguyên signed 32-bit.

GraphQL kiểm tra scalar input và áp dụng default trước khi gọi resolver. Argument bị bỏ qua khác với argument được truyền `null`; nếu cần phân biệt, dùng `ArgumentValue<T>`. Với kiểu dữ liệu đặc biệt như thời gian hoặc decimal, đăng ký custom scalar và coercion rõ ràng. Sau khi bind, service vẫn phải thực hiện validation nghiệp vụ và authorization.
