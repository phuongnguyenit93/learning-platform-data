# Binding nested input

## Mục tiêu

Sau bài học này, bạn có thể:

- Khai báo input object nhiều cấp trong GraphQL SDL.
- Phân biệt input object với object type dùng cho output.
- Gửi nested input bằng variables hoặc input literal.
- Bind input object lồng nhau vào Java record hoặc POJO bằng `@Argument`.
- Hiểu vai trò của `GraphQlArgumentBinder` trong việc bind object và collection đệ quy.
- Chọn constructor binding hoặc property binding phù hợp.
- Xử lý nullability, default value và trạng thái omitted/null.
- Áp dụng Bean Validation cho nested object và phần tử trong list.
- Kiểm thử binding và phân loại lỗi đầu vào.

## 1. Nested input là gì?

GraphQL mutation hoặc query có thể nhận một input object làm argument. Input object đó có thể chứa một input object khác hoặc danh sách input object. Cấu trúc này được gọi là nested input.

Ví dụ, khi tạo đơn hàng, client cần gửi thông tin khách hàng, địa chỉ giao hàng và các dòng sản phẩm:

~~~graphql
input ContactInput {
    email: String!
    phone: String
}

input CustomerInput {
    customerId: ID!
    contact: ContactInput!
}

input AddressInput {
    recipient: String!
    street: String!
    city: String!
    postalCode: String!
}

input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input CreateOrderInput {
    customer: CustomerInput!
    shippingAddress: AddressInput!
    lines: [OrderLineInput!]!
    note: String
}

type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}
~~~

`CreateOrderInput` chứa các cấu trúc lồng nhau:

- `customer` là một `CustomerInput`.
- `CustomerInput.contact` là một `ContactInput`.
- `shippingAddress` là một `AddressInput`.
- `lines` là danh sách các `OrderLineInput`.

Cách tổ chức này gom dữ liệu của cùng một thao tác vào một argument có tên rõ ràng. Client và server cùng sử dụng một cấu trúc dữ liệu thay vì truyền nhiều argument rời rạc.

## 2. Input object khác object type như thế nào?

GraphQL phân biệt type dùng để trả dữ liệu với type dùng để nhận dữ liệu.

`type` khai báo object type cho output:

~~~graphql
type Order {
    id: ID!
    status: String!
    total: Float!
}
~~~

`input` khai báo input object cho arguments:

~~~graphql
input CreateOrderInput {
    customer: CustomerInput!
    shippingAddress: AddressInput!
    lines: [OrderLineInput!]!
}
~~~

Không thể dùng trực tiếp object type làm kiểu field bên trong input object. Ví dụ sau không hợp lệ:

~~~graphql
type Address {
    street: String!
    city: String!
}

input CreateOrderInput {
    shippingAddress: Address
}
~~~

`Address` là object type dành cho output, không phải input type. Cần định nghĩa một input type riêng:

~~~graphql
input AddressInput {
    street: String!
    city: String!
}

input CreateOrderInput {
    shippingAddress: AddressInput!
}
~~~

Output type có thể chứa field chỉ đọc, field tính toán hoặc quan hệ mà client không được phép gửi lên. Input type chỉ nên chứa dữ liệu mà client được phép cung cấp cho thao tác đó. Không nên tái sử dụng output type làm input chỉ để giảm số lượng định nghĩa SDL.

## 3. Gửi nested input bằng variables

GraphQL variables được truyền dưới dạng JSON. JSON object lồng nhau tương ứng với các input object trong SDL.

Operation:

~~~graphql
mutation CreateOrder($input: CreateOrderInput!) {
    createOrder(input: $input) {
        id
        status
        total
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "customer": {
            "customerId": "customer-42",
            "contact": {
                "email": "an@example.com",
                "phone": "0900000000"
            }
        },
        "shippingAddress": {
            "recipient": "An Nguyen",
            "street": "12 Nguyen Hue",
            "city": "Ho Chi Minh City",
            "postalCode": "700000"
        },
        "lines": [
            {
                "productId": "product-10",
                "quantity": 2
            },
            {
                "productId": "product-25",
                "quantity": 1
            }
        ],
        "note": "Giao trong giờ hành chính"
    }
}
~~~

GraphQL runtime kiểm tra cấu trúc variables theo SDL trước khi gọi resolver. Tên field, kiểu scalar, input object và quy tắc non-null đều phải phù hợp với schema.

Nếu `shippingAddress` bị thiếu hoặc có giá trị `null` trong khi SDL khai báo `AddressInput!`, input không hợp lệ và resolver không được gọi.

## 4. Gửi nested input literal

Ngoài variables, GraphQL cho phép viết input object trực tiếp trong operation:

~~~graphql
mutation {
    createOrder(
        input: {
            customer: {
                customerId: "customer-42"
                contact: {
                    email: "an@example.com"
                    phone: "0900000000"
                }
            }
            shippingAddress: {
                recipient: "An Nguyen"
                street: "12 Nguyen Hue"
                city: "Ho Chi Minh City"
                postalCode: "700000"
            }
            lines: [
                { productId: "product-10", quantity: 2 }
                { productId: "product-25", quantity: 1 }
            ]
            note: "Giao trong giờ hành chính"
        }
    ) {
        id
        status
    }
}
~~~

Literal và variables tuân theo cùng cấu trúc SDL. Trong ứng dụng thực tế, variables thường thuận tiện hơn vì client có thể tạo JSON động, tái sử dụng operation và tránh ghép chuỗi query.

Dù dùng cách nào, server vẫn nhận dữ liệu đã qua GraphQL input coercion. Resolver không cần tự parse chuỗi GraphQL hoặc tự đọc JSON request body.

## 5. Bind nested input vào Java record

Spring for GraphQL dùng cơ chế argument binding để chuyển dữ liệu GraphQL thành kiểu Java mà method controller khai báo. `GraphQlArgumentBinder` hỗ trợ bind đệ quy input object, bao gồm object lồng nhau và collection.

Java record phù hợp khi input DTO chủ yếu chứa dữ liệu và không cần thay đổi sau khi tạo:

~~~java
public record ContactInput(
        String email,
        String phone) {
}

public record CustomerInput(
        String customerId,
        ContactInput contact) {
}

public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record OrderLineInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        CustomerInput customer,
        AddressInput shippingAddress,
        List<OrderLineInput> lines,
        String note) {
}
~~~

Các thành phần của record khớp với field trong SDL:

| GraphQL input field | Java record component |
| --- | --- |
| `CreateOrderInput.customer` | `CustomerInput customer` |
| `CustomerInput.contact` | `ContactInput contact` |
| `CreateOrderInput.shippingAddress` | `AddressInput shippingAddress` |
| `CreateOrderInput.lines` | `List<OrderLineInput> lines` |
| `OrderLineInput.quantity` | `Integer quantity` |

Khi bind `CreateOrderInput`, framework tiếp tục tạo `CustomerInput`, `ContactInput`, `AddressInput` và từng phần tử `OrderLineInput`. Tên field trong SDL cần khớp với tên component hoặc quy tắc binding mà DTO sử dụng.

## 6. Nhận nested input bằng @Argument

Method controller chỉ cần khai báo argument ở cấp field GraphQL. Spring sẽ bind toàn bộ object lồng nhau vào DTO:

~~~java
@Controller
class OrderMutationController {

    private final OrderService orderService;

    OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order createOrder(
            @Argument("input") CreateOrderInput input) {

        return orderService.create(input);
    }
}
~~~

`@Argument("input")` chỉ định argument `input` của field `Mutation.createOrder`. Không cần lặp lại annotation cho từng field con như `customer`, `contact` hoặc `shippingAddress`. Các field con được bind theo cấu trúc của `CreateOrderInput`.

Cần phân biệt hai schema:

~~~graphql
type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}
~~~

và:

~~~graphql
type Mutation {
    createOrder(
        customer: CustomerInput!
        shippingAddress: AddressInput!
        lines: [OrderLineInput!]!
    ): Order!
}
~~~

Cấu trúc đầu nhận một nested input object. Cấu trúc sau nhận nhiều arguments độc lập. Chữ ký Java phải tương ứng với SDL thực tế. Không dùng `@Argument("customer")` để lấy field con nếu schema chỉ khai báo một argument `input`.

## 7. Constructor binding và property binding

Spring argument binder có thể tạo đối tượng bằng constructor binding hoặc property binding.

**Constructor binding** tạo object thông qua constructor có các tham số tương ứng với input fields. Java record hoạt động tự nhiên với cách này vì record có canonical constructor chứa các record components.

~~~java
public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}
~~~

**Property binding** tạo object rồi gán giá trị vào các property có setter hoặc field phù hợp.

~~~java
public class AddressInput {

    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    public AddressInput() {
    }

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

Cả record và POJO đều có thể làm nested input DTO nếu cấu trúc và kiểu dữ liệu tương thích. Với class Java thông thường dùng constructor nhiều tham số, cần bảo đảm tên tham số constructor có thể được Spring đọc đúng, ví dụ giữ parameter names khi biên dịch hoặc dùng metadata constructor phù hợp.

Record phù hợp với input bất biến; POJO mutable phù hợp khi cần setter hoặc quy trình binding đặc biệt. Nên chọn một phong cách nhất quán trong cùng DTO.

## 8. Bind danh sách nested input

Input object có thể chứa danh sách các input object. Trong ví dụ đơn hàng, `lines` là một danh sách `OrderLineInput`.

SDL:

~~~graphql
input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input CreateOrderInput {
    lines: [OrderLineInput!]!
}
~~~

Java:

~~~java
public record OrderLineInput(
        String productId,
        Integer quantity) {
}
~~~

Trong `CreateOrderInput` ở ví dụ trước, component `lines` có kiểu `List<OrderLineInput>`. Spring bind từng phần tử trong danh sách thành `OrderLineInput`. Resolver nhận `List<OrderLineInput>` thay vì một danh sách Map cần tự chuyển đổi.

Nếu SDL khai báo `[OrderLineInput!]!`, danh sách không được null và từng phần tử không được null. Tuy nhiên, non-null không đồng nghĩa danh sách phải có ít nhất một phần tử. Quy tắc ít nhất một phần tử cần validation riêng, chẳng hạn `@NotEmpty`.

## 9. Kiểu scalar và conversion trong nested input

Các field scalar trong nested input được GraphQL coercion trước, sau đó Spring bind sang kiểu Java tương ứng.

~~~graphql
input ProductFilterInput {
    keyword: String
    minPrice: Float
    maxPrice: Float
    active: Boolean
    categoryIds: [ID!]!
}
~~~

~~~java
public record ProductFilterInput(
        String keyword,
        Double minPrice,
        Double maxPrice,
        Boolean active,
        List<String> categoryIds) {
}
~~~

Một số lưu ý:

- `String` thường bind với `String`.
- `Int` phù hợp với `Integer` hoặc kiểu số nguyên tương thích.
- `Float` có thể bind sang kiểu số phù hợp như `Double`.
- `Boolean` bind sang `Boolean`.
- `ID` thường được biểu diễn ở Java bằng `String`.
- Custom scalar cần coercing implementation và conversion phù hợp với kiểu Java đích.

Nếu sử dụng custom scalar như `UUID`, cần đăng ký scalar trong runtime wiring và kiểm tra kiểu Java mà scalar trả về. Không giả định rằng mọi scalar có biểu diễn JSON dạng chuỗi đều tự động bind thành bất kỳ Java type nào.

Với field nullable, dùng wrapper như `Integer`, `Double`, `Boolean` thay vì primitive nếu cần biểu diễn trạng thái null. Primitive Java không thể chứa null và có thể làm mất ý nghĩa của một field tùy chọn.

## 10. Nullability, omitted và default value

GraphQL phân biệt field bắt buộc và field tùy chọn thông qua `!`.

~~~graphql
input AddressInput {
    street: String!
    city: String!
    apartment: String
}

input CreateOrderInput {
    shippingAddress: AddressInput!
    note: String
}
~~~

- `shippingAddress: AddressInput!` bắt buộc phải có input object khác null.
- `street: String!` và `city: String!` là các field bắt buộc bên trong object.
- `apartment: String` có thể null hoặc bị bỏ qua.
- `note: String` có thể null hoặc bị bỏ qua.

GraphQL kiểm tra non-null trước khi resolver chạy. Nếu thiếu một field bắt buộc hoặc truyền null cho field non-null, input không hợp lệ.

Với field nullable, hai trạng thái có thể mang ý nghĩa khác nhau: client không gửi field, hoặc client gửi field với giá trị `null`. Khi bind vào property Java nullable thông thường, cả hai có thể trở thành `null`. Nếu nghiệp vụ cần phân biệt chúng, ví dụ trong thao tác cập nhật một phần, hãy dùng kiểu biểu diễn omitted/null mà Spring GraphQL hỗ trợ, chẳng hạn `ArgumentValue<T>`, tại vị trí binding phù hợp.

Ví dụ với một argument tùy chọn ở cấp field:

~~~graphql
type Mutation {
    renameBook(id: ID!, title: String): Book!
}
~~~

~~~java
@MutationMapping
public Book renameBook(
        @Argument("id") String id,
        @Argument("title") ArgumentValue<String> title) {

    if (title.isOmitted()) {
        return bookService.keepTitle(id);
    }

    if (title.value() == null) {
        return bookService.clearTitle(id);
    }

    return bookService.rename(id, title.value());
}
~~~

Với nested patch input, thiết kế DTO và wrapper để bảo toàn trạng thái omitted/null theo đúng khả năng binding của phiên bản Spring GraphQL đang dùng. Không dùng nullable Java property đơn giản nếu nghiệp vụ cần phân biệt "không thay đổi" với "xóa giá trị".

GraphQL cũng hỗ trợ default value trên input field:

~~~graphql
input SearchOptionsInput {
    page: Int = 0
    size: Int = 20
    includeArchived: Boolean = false
}

input SearchBooksInput {
    keyword: String!
    options: SearchOptionsInput!
}
~~~

Nếu client không truyền `page`, `size` hoặc `includeArchived`, GraphQL áp dụng default value khi coercion input theo schema. DTO nhận giá trị đã coercion theo schema. Tránh đặt default khác nhau ở SDL, DTO và service vì điều đó làm kết quả phụ thuộc vào đường gọi.

## 11. Validation cho nested input

GraphQL kiểm tra cấu trúc và kiểu dữ liệu theo SDL, nhưng không thay thế validation nghiệp vụ. Ví dụ `quantity: Int!` đảm bảo quantity là số nguyên khác null, nhưng không đảm bảo quantity lớn hơn 0.

Spring for GraphQL có thể kết hợp Bean Validation khi ứng dụng có validation provider và method argument được đánh dấu `@Valid` hoặc `@Validated`.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record ContactInput(
        @NotBlank @Email String email,
        String phone) {
}

public record CustomerInput(
        @NotBlank String customerId,
        @NotNull @Valid ContactInput contact) {
}

public record AddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank String postalCode) {
}

public record OrderLineInput(
        @NotBlank String productId,
        @Min(1) int quantity) {
}

public record CreateOrderInput(
        @NotNull @Valid CustomerInput customer,
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLineInput> lines,
        String note) {
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;

@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {

    return orderService.create(input);
}
~~~

`@Valid` trên method argument kích hoạt validation cho input object. Các annotation `@Valid` trên thuộc tính nested yêu cầu validation tiếp tục đi sâu vào object con. Với danh sách, `@Valid` trên type argument cho phép validate từng phần tử.

Cần có Bean Validation provider, thường được thêm qua `spring-boot-starter-validation` trong ứng dụng Spring Boot. Với Spring Boot 3, các annotation nằm trong package `jakarta.validation`.

### 11.1. Schema validation và Bean Validation

| Kiểm tra | GraphQL SDL | Bean Validation |
| --- | --- | --- |
| Field bắt buộc | `String!` | `@NotNull` |
| Chuỗi không rỗng | Không có quy tắc chuẩn tương đương | `@NotBlank` |
| Số nguyên | `Int` | Kiểu Java `Integer` |
| Số lượng tối thiểu | Không kiểm tra giá trị nghiệp vụ | `@Min(1)` |
| Email đúng định dạng | Không tự kiểm tra | `@Email` |
| Nested object | Input object và field type | `@Valid` để cascade |
| Danh sách có ít nhất một phần tử | Không chỉ bằng `[T!]!` | `@NotEmpty` |

GraphQL validation bảo vệ hợp đồng kiểu dữ liệu. Bean Validation kiểm tra thêm các ràng buộc về nội dung. Quy tắc phụ thuộc database hoặc trạng thái hệ thống, như sản phẩm còn hàng hay khách hàng được phép đặt hàng, vẫn cần kiểm tra trong service/domain layer.

## 12. Xử lý lỗi binding và validation

Lỗi có thể xuất hiện ở nhiều giai đoạn:

1. **GraphQL input coercion:** sai kiểu scalar, thiếu field non-null hoặc input object không hợp lệ.
2. **Spring argument binding:** dữ liệu GraphQL không thể chuyển thành cấu trúc Java đích.
3. **Bean Validation:** object bind thành công nhưng vi phạm constraint.
4. **Business validation:** dữ liệu hợp lệ về cấu trúc nhưng không thỏa mãn nghiệp vụ.

| Dữ liệu đầu vào | Tầng phát hiện |
| --- | --- |
| `quantity` truyền chuỗi `"many"` thay vì số nguyên | GraphQL coercion |
| DTO yêu cầu constructor/property không thể bind | Argument binding |
| `email` không đúng định dạng | Bean Validation |
| `quantity` bằng `0` khi cần tối thiểu `1` | Bean Validation hoặc business validation |
| Sản phẩm không tồn tại | Service/repository |
| Sản phẩm đã hết hàng | Business validation |

Spring GraphQL chuyển lỗi binding hoặc validation thành GraphQL errors theo cơ chế xử lý lỗi của framework. Ứng dụng có thể tùy chỉnh cách biểu diễn lỗi bằng `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler`.

Không nên trả stack trace, tên bảng database hoặc thông tin nội bộ trong error message. Có thể trả thông báo validation thân thiện cho client và ghi chi tiết kỹ thuật vào log có kiểm soát. Không tự biến input không hợp lệ thành object rỗng hoặc âm thầm bỏ qua field sai.

## 13. Không bind input trực tiếp vào entity persistence

Một cách làm có vẻ nhanh là nhận entity database trực tiếp làm input:

~~~java
@MutationMapping
public Order createOrder(@Argument("input") OrderEntity input) {
    return repository.save(input);
}
~~~

Cách này có thể khiến client gửi những thuộc tính mà họ không nên điều khiển, ví dụ:

- `id` do server sinh.
- `status` chỉ backend được thay đổi.
- `createdAt`, `updatedAt`.
- `tenantId` hoặc `ownerId`.
- Các quan hệ nội bộ hoặc cờ quản trị.

Nên dùng input DTO riêng:

~~~java
public record CreateOrderInput(
        CustomerInput customer,
        AddressInput shippingAddress,
        List<OrderLineInput> lines,
        String note) {
}
~~~

Sau đó service chuyển input thành domain/entity theo chính sách của server:

~~~java
@Service
class OrderService {

    public Order create(CreateOrderInput input) {
        OrderEntity entity = new OrderEntity();

        entity.setCustomerId(input.customer().customerId());
        entity.setShippingAddress(mapAddress(input.shippingAddress()));
        entity.setLines(mapLines(input.lines()));
        entity.setNote(input.note());

        // ID, tenant, owner, status và timestamps
        // được xác định theo quy tắc phía server.
        return repository.save(entity);
    }
}
~~~

Input DTO tạo ranh giới rõ ràng giữa dữ liệu client được phép gửi và trạng thái nội bộ của hệ thống. Không dùng dữ liệu client gửi lên làm nguồn tin cậy cho owner hoặc tenant nếu các giá trị đó phải được xác định từ security context.

## 14. Kiểm thử nested input binding

Nên kiểm thử qua GraphQL operation để xác minh SDL, argument binder và controller cùng hoạt động.

Ví dụ với `GraphQlTester`:

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
                "customer", Map.of(
                        "customerId", "customer-42",
                        "contact", Map.of(
                                "email", "an@example.com",
                                "phone", "0900000000"
                        )
                ),
                "shippingAddress", Map.of(
                        "recipient", "An Nguyen",
                        "street", "12 Nguyen Hue",
                        "city", "Ho Chi Minh City",
                        "postalCode", "700000"
                ),
                "lines", List.of(
                        Map.of("productId", "product-10", "quantity", 2),
                        Map.of("productId", "product-25", "quantity", 1)
                ),
                "note", "Giao trong giờ hành chính"
        ))
        .execute()
        .path("createOrder.status")
        .entity(String.class)
        .isEqualTo("CREATED");
~~~

Test này xác minh nested variables được bind thành DTO và mutation trả về kết quả mong đợi.

Các trường hợp nên có:

- Nested object đủ field hợp lệ.
- Nested object bị thiếu field non-null.
- Field nullable bị bỏ qua.
- Field nullable được truyền `null`.
- Danh sách nested object có nhiều phần tử.
- Một phần tử trong list sai kiểu hoặc thiếu field bắt buộc.
- Bean Validation thất bại ở cấp object con.
- Bean Validation thất bại ở phần tử trong list.
- Custom scalar trong nested input được coercion đúng.
- Input không hợp lệ không làm service ghi dữ liệu.

Unit test DTO không xác minh được tên field SDL, quá trình GraphQL coercion hoặc việc Spring bind đúng nested object. Một integration test qua `GraphQlTester` nên là lớp xác minh chính cho đường đi từ GraphQL variables đến Java argument.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@Argument` nhận null | Tên argument không khớp SDL hoặc client không gửi input | Kiểm tra tên argument và variables |
| Nested object con nhận null | Tên field SDL không khớp property/constructor component | Đối chiếu từng cấp tên field |
| Không bind được Java record | Constructor component hoặc kiểu Java không tương thích | Kiểm tra tên component và kiểu dữ liệu |
| POJO có property null dù client đã gửi | Thiếu setter/constructor phù hợp hoặc property binding không hoạt động như mong đợi | Dùng record hoặc bổ sung setter/constructor |
| Danh sách bind sai phần tử | Generic element type không tương thích với input object | Dùng `List<SpecificInput>` và kiểm tra SDL |
| Dùng output `type` trong input | GraphQL không cho phép object type làm input field | Khai báo `input` type riêng |
| Field bắt buộc bị bỏ qua | Vi phạm non-null trong SDL | Kiểm tra `!` và payload |
| Không phân biệt omitted với null | DTO dùng property nullable thông thường | Dùng cơ chế `ArgumentValue` khi cần phân biệt |
| Validation nested object không chạy | Thiếu `@Valid` ở argument hoặc thuộc tính con | Bổ sung cascade validation |
| Danh sách rỗng vẫn qua schema | `[T!]!` không bắt buộc có phần tử | Dùng `@NotEmpty` hoặc business validation |
| Client gửi được owner/tenant không mong muốn | Input DTO phơi bày field nội bộ | Tách input DTO và xác định giá trị tin cậy ở server |

## 16. Quy trình thiết kế nested input

Khi thiết kế một mutation nhận dữ liệu nhiều cấp, hãy thực hiện theo trình tự:

1. **Xác định dữ liệu client được phép gửi.** Tách field công khai khỏi trạng thái nội bộ.
2. **Thiết kế input object.** Chia thành các input type nhỏ theo nhóm dữ liệu có ý nghĩa.
3. **Khai báo nullability.** Dùng `!` cho field bắt buộc và xác định default value nếu có.
4. **Chọn cấu trúc Java.** Dùng record cho DTO bất biến hoặc POJO khi cần property binding.
5. **Giữ tên nhất quán.** Đối chiếu tên field trong SDL với component, constructor hoặc property Java.
6. **Bind ở cấp argument.** Dùng `@Argument` cho input object cấp field; binder xử lý các cấp lồng nhau.
7. **Thêm validation.** Dùng `@Valid` và constraint cho các quy tắc cấu trúc, sau đó kiểm tra nghiệp vụ trong service.
8. **Xử lý omitted và null.** Chọn DTO/wrapper phù hợp nếu thao tác cập nhật cần phân biệt hai trạng thái.
9. **Chuyển input sang domain.** Không để client trực tiếp điều khiển field nội bộ của entity.
10. **Kiểm thử bằng GraphQL operation.** Bao gồm nested object, list, lỗi binding và validation.

## 17. Tổng kết

Nested input cho phép một GraphQL argument chứa input object nhiều cấp và danh sách input object. SDL dùng `input` để định nghĩa cấu trúc dữ liệu client được phép gửi; object type dùng `type` dành cho output và không thể thay thế input type.

Trong Spring for GraphQL, `@Argument` nhận input object cấp field, còn `GraphQlArgumentBinder` bind đệ quy các nested object và collection vào Java record hoặc POJO. Tên field và kiểu dữ liệu phải tương thích ở từng cấp. GraphQL coercion kiểm tra cấu trúc và nullability; Bean Validation kiểm tra constraint như email, số lượng và nested object; service tiếp tục kiểm tra nghiệp vụ. Dùng input DTO riêng, xử lý rõ omitted/null và kiểm thử bằng `GraphQlTester` giúp quá trình binding an toàn, dễ hiểu và dễ bảo trì.

