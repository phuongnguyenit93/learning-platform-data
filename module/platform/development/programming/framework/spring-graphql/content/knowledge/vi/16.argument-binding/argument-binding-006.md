# Binding input object

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của GraphQL input object và phân biệt nó với object type dùng cho dữ liệu trả về.
- Khai báo input type có field scalar, enum, object lồng nhau và danh sách.
- Dùng `@Argument` để bind input object vào Java record hoặc DTO.
- Hiểu cách `GraphQlArgumentBinder` tạo object và chuyển đổi dữ liệu lồng nhau.
- Xử lý giá trị mặc định, nullable, omitted và explicit null.
- Kết hợp Bean Validation với input DTO.
- Nhận biết lỗi GraphQL validation, lỗi binding và lỗi nghiệp vụ.
- Kiểm thử quá trình binding bằng `GraphQlTester`.

## 1. Input object dùng để làm gì?

GraphQL input object là kiểu dữ liệu dành cho đầu vào của operation. Nó gom nhiều giá trị liên quan vào một cấu trúc có tên, giúp mutation hoặc query nhận dữ liệu phức tạp mà không cần khai báo quá nhiều argument rời rạc.

Ví dụ, tạo đơn hàng cần mã khách hàng, địa chỉ giao hàng, danh sách mặt hàng và phương thức vận chuyển. Có thể khai báo từng argument trên mutation, nhưng schema sẽ dài và khó mở rộng. Input object giúp nhóm dữ liệu đó thành một đơn vị:

~~~graphql
input CreateOrderInput {
  customerId: ID!
  shippingAddress: AddressInput!
  items: [OrderLineInput!]!
  shippingMethod: ShippingMethod!
}

input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
}

enum ShippingMethod {
  STANDARD
  EXPRESS
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Client truyền dữ liệu trong một biến:

~~~graphql
mutation CreateOrder($input: CreateOrderInput!) {
  createOrder(input: $input) {
    id
    status
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "customerId": "customer-42",
    "shippingAddress": {
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    },
    "items": [
      {
        "productId": "book-01",
        "quantity": 2
      },
      {
        "productId": "book-02",
        "quantity": 1
      }
    ],
    "shippingMethod": "EXPRESS"
  }
}
~~~

Input object làm cho hợp đồng đầu vào rõ ràng, có kiểu và có thể tái sử dụng ở nhiều mutation nếu cùng ngữ nghĩa.

## 2. Phân biệt input type và object type

GraphQL phân biệt rõ kiểu dùng để nhận dữ liệu và kiểu dùng để trả dữ liệu.

- **Object type** mô tả dữ liệu server trả về cho client. Field của object type có thể có argument và có thể tham chiếu interface hoặc union.
- **Input object type** mô tả cấu trúc dữ liệu client được phép gửi vào. Field của input object không có argument và chỉ được dùng các kiểu đầu vào hợp lệ.

Ví dụ:

~~~graphql
type Order {
  id: ID!
  status: OrderStatus!
  total: Money!
}

input CreateOrderInput {
  customerId: ID!
  shippingAddress: AddressInput!
}
~~~

Không thể dùng `Order` làm kiểu argument input chỉ vì nó có các field cần thiết. Tương tự, không thể dùng `CreateOrderInput` làm kiểu trả về của mutation.

Các kiểu được phép xuất hiện trong input object gồm:

- Scalar tích hợp như `String`, `Int`, `Float`, `Boolean`, `ID`.
- Custom scalar đã khai báo.
- Enum.
- Input object khác.
- Danh sách của các kiểu đầu vào hợp lệ.

Input object không thể chứa object type, interface hoặc union. Quy tắc này ngăn client gửi một cấu trúc có field đầu ra phức tạp hoặc các quan hệ không phù hợp với input.

## 3. Bind input object vào Java bằng @Argument

Trong Spring for GraphQL, `@Argument` đánh dấu tham số method nhận giá trị từ argument của GraphQL field.

SDL:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publishedYear: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java DTO:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}
~~~

Controller:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Spring for GraphQL lấy giá trị argument `input`, sau đó bind cấu trúc dữ liệu vào `CreateBookInput`. Method nhận được object Java đã được tạo và có thể chuyển tiếp cho service.

Tên trong `@Argument("input")` phải khớp argument trên field `Mutation.createBook`. Nếu không truyền tên tường minh, Spring có thể suy ra từ tên tham số Java khi thông tin tên tham số được giữ trong bytecode. Với API quan trọng, khai báo tên rõ ràng giúp tránh phụ thuộc vào cấu hình biên dịch.

Không nên nhận toàn bộ JSON request dưới dạng chuỗi rồi tự parse nếu GraphQL schema đã mô tả cấu trúc đó. Dùng input type và `@Argument` giúp tận dụng validation kiểu của GraphQL và cơ chế binding của Spring.

## 4. GraphQlArgumentBinder hoạt động như thế nào?

Spring for GraphQL dùng `GraphQlArgumentBinder` để chuyển dữ liệu argument đã được GraphQL engine parse thành object Java.

Quá trình binding có thể hiểu qua các bước:

1. GraphQL kiểm tra operation theo schema và coercion các giá trị đầu vào.
2. Spring lấy giá trị của argument tương ứng với `@Argument`.
3. Binder đọc cấu trúc Map, list và các giá trị scalar đã được chuyển đổi.
4. Binder tạo object đích bằng constructor binding nếu có constructor phù hợp.
5. Với kiểu mutable phù hợp, binder có thể dùng constructor mặc định rồi bind property thông qua setter hoặc field.
6. Nếu dữ liệu lồng nhau không bind được, lỗi binding được ghi nhận và đưa vào quá trình xử lý lỗi.

Với Java record, constructor canonical là lựa chọn tự nhiên vì record bất biến và khai báo rõ các thành phần dữ liệu:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}
~~~

Với class mutable, có thể dùng constructor mặc định và setter:

~~~java
public class CreateBookInput {

    private String title;
    private String authorId;
    private Integer publishedYear;

    public CreateBookInput() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthorId() {
        return authorId;
    }

    public void setAuthorId(String authorId) {
        this.authorId = authorId;
    }

    public Integer getPublishedYear() {
        return publishedYear;
    }

    public void setPublishedYear(Integer publishedYear) {
        this.publishedYear = publishedYear;
    }
}
~~~

Với class dùng constructor nhiều tham số, tên tham số cần được Spring nhận diện để ghép đúng input field. Có thể dùng record, cấu hình biên dịch giữ tên tham số hoặc metadata constructor phù hợp. Đừng giả định thứ tự field trong JSON sẽ luôn được dùng để gán theo vị trí.

## 5. Binding input object lồng nhau

Input object có thể chứa input object khác. Cấu trúc Java cần phản ánh đúng hình dạng của SDL.

SDL:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input CreateCustomerInput {
  fullName: String!
  email: String!
  address: AddressInput!
}

type Mutation {
  createCustomer(input: CreateCustomerInput!): Customer!
}
~~~

Java records:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateCustomerInput(
        String fullName,
        String email,
        AddressInput address) {
}
~~~

Controller:

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument("input") CreateCustomerInput input) {
    return customerService.create(input);
}
~~~

Khi client gửi input có object `address`, binder tiếp tục tạo `AddressInput` và gắn vào `CreateCustomerInput`.

Cấu trúc lồng nhau có thể sâu nhiều cấp, nhưng nên giữ ở mức phản ánh domain. Input quá sâu hoặc chứa nhiều nhánh tùy chọn có thể khiến client khó xây dựng và khó hiểu quy tắc validation.

Nếu một object lồng nhau được dùng ở nhiều mutation và có cùng ý nghĩa, có thể tái sử dụng input type. Chỉ nên tái sử dụng khi hợp đồng và ngữ nghĩa thực sự giống nhau; không nên ghép các input khác mục đích chỉ để giảm số type.

## 6. Binding list và enum

Input object thường chứa danh sách phần tử và enum. Java DTO nên dùng generic type cụ thể để binder biết kiểu phần tử cần tạo.

SDL:

~~~graphql
enum ShippingMethod {
  STANDARD
  EXPRESS
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  shippingMethod: ShippingMethod!
  items: [OrderLineInput!]!
}
~~~

Java:

~~~java
public enum ShippingMethod {
    STANDARD,
    EXPRESS
}

public record OrderLineInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        ShippingMethod shippingMethod,
        List<OrderLineInput> items) {
}
~~~

Với enum, tên value trong SDL cần tương thích với tên Java enum constant hoặc được cấu hình mapping phù hợp. Với list, `List<OrderLineInput>` cho phép binder tạo từng phần tử thành DTO thay vì để lại các Map không có kiểu.

Không nên khai báo raw type như `List items` nếu cần binding phần tử thành object. Dùng generic type cụ thể giúp code dễ đọc, dễ kiểm tra và tránh cast thủ công.

## 7. Scalar coercion diễn ra trước Java binding

GraphQL engine chịu trách nhiệm parse và coercion giá trị theo kiểu scalar trong schema. Sau đó Spring binder mới chuyển các giá trị đã được coercion vào tham số Java.

Ví dụ:

~~~graphql
input CreateBookInput {
  title: String!
  publishedYear: Int
  authorId: ID!
}
~~~

DTO:

~~~java
public record CreateBookInput(
        String title,
        Integer publishedYear,
        String authorId) {
}
~~~

Trong ví dụ này:

- `String` được bind vào Java `String`.
- `Int` được bind vào `Integer`.
- `ID` thường được nhận dưới dạng Java `String`.

Nếu dùng custom scalar như `Date` hoặc `DateTime`, scalar coercing phải được đăng ký trong runtime wiring. Khi GraphQL engine đã chuyển giá trị sang `LocalDate` hoặc `OffsetDateTime`, binder có thể gán giá trị đó vào DTO có kiểu tương ứng.

Không nên kỳ vọng binder tự đoán mọi định dạng chuỗi tùy chỉnh. Hãy để scalar định nghĩa cách parse và serialize dữ liệu theo hợp đồng schema.

## 8. Required, nullable và giá trị mặc định

Dấu `!` trong SDL quy định giá trị có được phép null hay không. Java DTO cần chọn kiểu tương ứng.

| SDL | Ý nghĩa | Java thường dùng |
|---|---|---|
| `String!` | Bắt buộc, không null | `String` với validation/nghiệp vụ phù hợp |
| `String` | Có thể null | `String` |
| `Int!` | Bắt buộc, không null | `Integer` hoặc `int` |
| `Int` | Có thể null | `Integer` |
| `[Item!]!` | List bắt buộc, từng phần tử không null | `List<ItemInput>` |
| `[Item]` | List và phần tử đều có thể null | Cấu trúc Java cần xử lý null ở cả hai cấp |

Với field nullable, dùng wrapper/reference type để biểu diễn null. Không nên dùng primitive cho giá trị có thể bị bỏ trống vì primitive không thể nhận null.

### Giá trị mặc định trong SDL

Có thể khai báo default value cho argument hoặc input field:

~~~graphql
input SearchOptions {
  includeArchived: Boolean = false
  pageSize: Int = 20
}

type Query {
  searchBooks(options: SearchOptions): [Book!]!
}
~~~

Khi client bỏ qua field có default value, GraphQL áp dụng giá trị mặc định theo quy tắc input coercion. Khi Java nhận argument, cần hiểu rằng giá trị mặc định đã được áp dụng ở tầng GraphQL; không nên lặp lại một default khác trong DTO mà không có chủ đích.

Default value chỉ có ý nghĩa khi omission được phép. Field non-null không có default phải được cung cấp bởi client hoặc được truyền qua biến/argument theo quy tắc của GraphQL.

## 9. Phân biệt omitted và explicit null bằng ArgumentValue

Trong input, có hai trạng thái khác nhau:

- **Omitted:** client không gửi field.
- **Explicit null:** client gửi field với giá trị null.

Với mutation cập nhật một phần, hai trạng thái này có thể mang ý nghĩa khác nhau. Ví dụ, bỏ qua `subtitle` nghĩa là giữ nguyên; gửi `subtitle: null` nghĩa là xóa giá trị hiện tại.

SDL:

~~~graphql
type Mutation {
  updateBookSubtitle(
    id: ID!
    subtitle: String
  ): Book!
}
~~~

Controller có thể dùng `ArgumentValue<T>`:

~~~java
@MutationMapping
public Book updateBookSubtitle(
        @Argument String id,
        @Argument ArgumentValue<String> subtitle) {

    if (subtitle.isOmitted()) {
        return bookService.findById(id);
    }

    return bookService.updateSubtitle(id, subtitle.value());
}
~~~

`ArgumentValue` cho phép kiểm tra argument có được truyền hay không. Khi argument được truyền rõ ràng với null, `isOmitted()` là false và `value()` là null. Khi argument không xuất hiện, `isOmitted()` là true.

Hai request có ý nghĩa khác nhau:

~~~graphql
mutation {
  updateBookSubtitle(id: "b-01") {
    id
  }
}
~~~

~~~graphql
mutation {
  updateBookSubtitle(id: "b-01", subtitle: null) {
    id
  }
}
~~~

Cách tiếp cận này hữu ích với PATCH-style mutation. Với input object phức tạp, hãy thiết kế chiến lược biểu diễn omitted/null phù hợp và kiểm thử từng field; không nên tự động xem mọi field nullable bị thiếu là yêu cầu xóa dữ liệu.

## 10. Validation cho input DTO

GraphQL validation kiểm tra kiểu và cấu trúc theo SDL, nhưng không thay thế validation nghiệp vụ. Ví dụ, `quantity: Int!` bảo đảm có một số nguyên không null, nhưng không tự bảo đảm quantity lớn hơn 0.

Có thể dùng Jakarta Bean Validation trên DTO:

~~~java
public record OrderLineInput(
        @NotBlank String productId,
        @NotNull @Positive Integer quantity) {
}

public record AddressInput(
        @NotBlank String street,
        @NotBlank String city,
        String postalCode) {
}

public record CreateOrderInput(
        @NotBlank String customerId,
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLineInput> items,
        @NotNull ShippingMethod shippingMethod) {
}
~~~

Controller đánh dấu input cần validate:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Khi ứng dụng có Bean Validation implementation phù hợp, Spring for GraphQL có thể áp dụng validation cho method argument được đánh dấu. Các constraint lồng nhau cần `@Valid` để kích hoạt cascade validation.

Một số annotation thường dùng:

| Annotation | Ý nghĩa |
|---|---|
| `@NotNull` | Không cho phép null |
| `@NotBlank` | Chuỗi không null và có ký tự không phải khoảng trắng |
| `@Positive` | Số phải lớn hơn 0 |
| `@Size` | Giới hạn độ dài hoặc kích thước |
| `@Email` | Kiểm tra định dạng email cơ bản |
| `@Valid` | Kích hoạt validation cho object lồng nhau |

SDL nên mô tả ràng buộc cấu trúc như required và scalar type. Bean Validation mô tả thêm quy tắc dữ liệu. Service vẫn cần kiểm tra quy tắc domain có liên quan đến trạng thái hiện tại, quyền người dùng hoặc dữ liệu trong database.

## 11. Phân biệt GraphQL validation, binding error và business error

Một request có thể thất bại ở các giai đoạn khác nhau.

| Giai đoạn | Ví dụ | Nơi xử lý |
|---|---|---|
| GraphQL parse/validation | Sai cú pháp, field không tồn tại, thiếu argument non-null | GraphQL engine trước khi gọi resolver |
| Scalar coercion | Truyền chuỗi không parse được thành Int hoặc Date | Scalar coercing của GraphQL Java |
| Argument binding | Không tạo được DTO hoặc không bind được property lồng | `GraphQlArgumentBinder` và cơ chế xử lý lỗi |
| Bean Validation | Quantity bằng 0, email không hợp lệ | Jakarta Bean Validation |
| Business validation | Sản phẩm ngừng bán, người dùng không có quyền đặt hàng | Service/domain layer |

Ví dụ, client gửi `quantity: "many"` trong khi SDL khai báo `Int!`. GraphQL có thể từ chối ở bước coercion trước khi controller chạy.

Nếu client gửi số nguyên hợp lệ là 0, GraphQL chấp nhận kiểu dữ liệu. Bean Validation với `@Positive` mới phát hiện quantity không hợp lệ theo nghiệp vụ.

Nếu quantity là 2 nhưng sản phẩm đã hết hàng, chỉ service/domain mới có đủ thông tin để từ chối thao tác.

Không nên gom mọi lỗi thành một thông báo chung. Hãy phân biệt lỗi cấu trúc, lỗi dữ liệu và lỗi nghiệp vụ để client có thể sửa request hoặc hiển thị phản hồi phù hợp. Thông báo lỗi công khai không nên chứa SQL, stack trace hoặc thông tin nhạy cảm.

## 12. Dùng Map khi cần input động

Trong một số trường hợp, cấu trúc input có thể thay đổi theo cấu hình hoặc cần xử lý động. Khi đó, có thể nhận argument dưới dạng Map:

~~~java
@MutationMapping
public Result executeDynamic(
        @Argument("payload") Map<String, Object> payload) {
    return dynamicService.execute(payload);
}
~~~

SDL vẫn cần khai báo input object hợp lệ:

~~~graphql
input DynamicPayload {
  action: String!
  attributes: [AttributeInput!]
}

input AttributeInput {
  name: String!
  value: String
}

type Mutation {
  executeDynamic(payload: DynamicPayload!): Result!
}
~~~

Map giúp truy cập key động nhưng làm giảm an toàn kiểu. Code phải tự kiểm tra key, kiểu giá trị, cấu trúc lồng và quy tắc nghiệp vụ. Không nên dùng Map cho mọi input chỉ để giảm số DTO.

Nếu schema đã ổn định, record hoặc DTO cụ thể thường dễ bảo trì hơn, hỗ trợ IDE và validation tốt hơn.

## 13. Không bind trực tiếp input vào JPA entity

Không nên dùng entity persistence làm input DTO công khai chỉ vì các field có vẻ giống nhau.

Ví dụ, entity Order có thể chứa:

- `id` do server tạo.
- `status` do quy trình nghiệp vụ quản lý.
- `createdAt` và `updatedAt`.
- `customer` hoặc quan hệ nội bộ.
- Các field audit hoặc quyền sở hữu.

Nếu client được bind trực tiếp vào entity, có nguy cơ client truyền các field mà họ không được phép thay đổi. Đây là dạng mass assignment.

Nên tạo input DTO chỉ chứa các field client được phép gửi:

~~~java
public record CreateOrderInput(
        String customerId,
        AddressInput shippingAddress,
        List<OrderLineInput> items,
        ShippingMethod shippingMethod) {
}
~~~

Service kiểm tra quyền, tải dữ liệu liên quan và tạo entity theo quy tắc nghiệp vụ:

~~~java
public Order create(CreateOrderInput input, UserPrincipal principal) {
    // Kiểm tra quyền đặt hàng thay mặt customer.
    // Tải sản phẩm và kiểm tra tồn kho.
    // Tính tổng tiền phía server.
    // Tạo Order với status và audit field do server quản lý.
}
~~~

Client không nên được tự quyết định giá cuối cùng, trạng thái đơn hàng hoặc thông tin audit nếu các giá trị đó do server kiểm soát.

## 14. Kiểm thử input binding bằng GraphQlTester

Integration test nên gửi GraphQL operation với variables để kiểm tra cả coercion, binding và resolver.

Ví dụ:

~~~java
@Test
void shouldBindNestedCreateBookInput() {
    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                    author {
                        id
                    }
                }
            }
            """)
            .variable("input", Map.of(
                    "title", "GraphQL in Practice",
                    "authorId", "author-01",
                    "publishedYear", 2026))
            .execute()
            .path("createBook.title")
            .entity(String.class)
            .isEqualTo("GraphQL in Practice");
}
~~~

Với input lồng nhau, có thể truyền Map trong test để thể hiện chính xác cấu trúc JSON mà client gửi.

Nên có test cho các trường hợp:

1. Input object hợp lệ được bind thành record/DTO.
2. Input object lồng nhau được bind đúng.
3. List và enum được chuyển đổi đúng.
4. Field bắt buộc bị thiếu bị GraphQL từ chối.
5. Scalar sai kiểu bị coercion từ chối.
6. Field nullable nhận explicit null.
7. Argument bị bỏ qua được phân biệt bằng `ArgumentValue`.
8. Bean Validation từ chối dữ liệu không hợp lệ.
9. Binding error được trả về theo định dạng GraphQL errors phù hợp.
10. Service từ chối vi phạm nghiệp vụ như hết hàng hoặc thiếu quyền.

Ví dụ kiểm tra request sai:

~~~java
@Test
void shouldRejectInvalidQuantity() {
    graphQlTester.document("""
            mutation {
                createOrder(input: {
                    customerId: "customer-42"
                    shippingAddress: {
                        street: "12 Nguyen Hue"
                        city: "Ho Chi Minh City"
                    }
                    items: [{
                        productId: "book-01"
                        quantity: 0
                    }]
                    shippingMethod: EXPRESS
                }) {
                    id
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

Test trên giả định DTO có `@Positive` và validation được bật. Trong test thực tế, nên kiểm tra cả mã lỗi hoặc error classification mà ứng dụng công bố, không chỉ kiểm tra danh sách errors khác rỗng.

## 15. Nguyên tắc thiết kế input object

Khi thiết kế GraphQL input và Java DTO, hãy lưu ý:

- Tạo input type riêng cho dữ liệu client gửi vào.
- Không dùng object type, interface hoặc union ở vị trí input.
- Dùng record hoặc DTO có cấu trúc rõ ràng để binding.
- Dùng `@Argument("input")` với tên argument tường minh.
- Giữ kiểu Java phù hợp với scalar, enum, list và nullability của SDL.
- Dùng generic type cụ thể cho collection lồng nhau.
- Dùng `ArgumentValue<T>` khi cần phân biệt omitted và explicit null.
- Dùng Bean Validation cho constraint dữ liệu và service cho quy tắc domain.
- Không bind trực tiếp vào JPA entity có field nhạy cảm hoặc do server quản lý.
- Kiểm thử input hợp lệ, thiếu field, sai kiểu, null, binding error và business error.

Một input object tốt thể hiện đúng dữ liệu client được phép cung cấp. Nó không nên là bản sao toàn bộ entity hoặc một cấu trúc quá rộng khiến server khó kiểm soát quyền thay đổi.

## Kết luận

Binding input object là quá trình chuyển dữ liệu đầu vào đã được GraphQL kiểm tra kiểu thành Java object mà controller và service có thể sử dụng. Trong Spring for GraphQL, `@Argument` kết hợp với `GraphQlArgumentBinder` hỗ trợ bind scalar, enum, list, DTO và cấu trúc input lồng nhau.

Dùng Java record hoặc DTO giúp giữ cấu trúc rõ ràng và an toàn kiểu. Kết hợp SDL nullability, `ArgumentValue`, Bean Validation và kiểm tra domain giúp xử lý đúng các trường hợp thiếu dữ liệu, explicit null, dữ liệu sai định dạng và vi phạm nghiệp vụ. Khi kiểm thử bằng `GraphQlTester`, hãy bao phủ toàn bộ đường đi từ variables đến object Java và kết quả mutation.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers and Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — GraphQlArgumentBinder API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/GraphQlArgumentBinder.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
