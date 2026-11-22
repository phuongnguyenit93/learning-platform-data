# Thiết kế tên field ổn định trong Spring for GraphQL

Tên field trong GraphQL là một phần của hợp đồng API mà client sử dụng trực tiếp. Client viết query bằng những tên này, code generation tạo property từ chúng, tài liệu API hiển thị chúng và các operation đã lưu có thể tiếp tục phụ thuộc vào chúng trong nhiều năm. Vì vậy, đổi tên field là một thay đổi hợp đồng, ngay cả khi Java method, DTO hoặc database column phía server chỉ cần đổi một dòng.

Một schema tốt dùng tên dễ hiểu, nhất quán và phản ánh đúng ý nghĩa nghiệp vụ. Khi yêu cầu thay đổi, API nên tiến hóa theo hướng bổ sung field mới, đánh dấu field cũ deprecated và cho client thời gian chuyển đổi. Không nên đổi ý nghĩa của một field đang tồn tại chỉ để tái sử dụng tên cũ.

## 1. Tên field là public contract

Giả sử schema công khai:

~~~graphql
type Query {
    user(id: ID!): User
}

type User {
    id: ID!
    name: String!
    email: String!
}
~~~

Client có thể lưu operation:

~~~graphql
query UserProfile($id: ID!) {
    user(id: $id) {
        id
        name
        email
    }
}
~~~

Tên `User.name` không chỉ là tên một property Java. Nó có thể xuất hiện trong:

- Query và mutation của nhiều ứng dụng client.
- Fragment được tái sử dụng trong nhiều operation.
- TypeScript/Kotlin/Swift types được sinh từ schema.
- Persisted query, test fixture và tài liệu tích hợp.
- Dashboard theo dõi field usage hoặc lỗi resolver.
- Các service khác gọi supergraph/subgraph.

Nếu đổi `name` thành `fullName`, mọi client còn query `name` có thể gặp validation error. Server vẫn compile thành công không có nghĩa API không bị phá vỡ.

Hãy xem tên field như tên của một hàm public hoặc cột trong message contract: đã công bố thì cần có chiến lược tiến hóa.

## 2. GraphQL quy định cú pháp tên, không áp đặt quy ước đặt tên

GraphQL specification quy định một tên có thể chứa chữ cái ASCII, chữ số và dấu gạch dưới theo vị trí hợp lệ. Tên GraphQL phân biệt chữ hoa/chữ thường: `name`, `Name` và `NAME` là ba tên khác nhau. Tên trong type system không được bắt đầu bằng hai dấu gạch dưới `__`, vì tiền tố này dành cho introspection.

Specification không bắt buộc tất cả schema phải dùng camelCase hay PascalCase. Đó là quy ước thiết kế được chọn để schema nhất quán và dễ dùng. Một bộ quy ước phổ biến:

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Field | `camelCase` | `firstName`, `createdAt` |
| Argument | `camelCase` | `userId`, `includeArchived` |
| Type, interface, union | `PascalCase` | `User`, `OrderConnection`, `SearchResult` |
| Enum type | `PascalCase` | `OrderStatus` |
| Enum value | `SCREAMING_SNAKE_CASE` | `IN_PROGRESS`, `CANCELLED` |
| Directive | `camelCase` | `@requiresRole` |

Điều quan trọng hơn việc chọn một kiểu viết cụ thể là áp dụng nhất quán trong toàn schema. Không tạo một field `createdAt`, field khác `created_at`, và field thứ ba `CreatedAt` cho cùng một khái niệm.

## 3. Đặt tên theo ý nghĩa nghiệp vụ

Tên field nên mô tả dữ liệu mà client nhận được, không mô tả cách server lấy dữ liệu.

| Tên kém rõ ràng | Tên dễ hiểu hơn | Lý do |
| --- | --- | --- |
| `getUser` | `user` | Query đã thể hiện hành động đọc |
| `fetchOrders` | `orders` | Field mô tả collection trả về |
| `usrNm` | `userName` hoặc `fullName` | Tránh viết tắt theo database |
| `data` | `profile` hoặc `orderSummary` | Tên cụ thể hơn về nội dung |
| `status` | `paymentStatus` hoặc `orderStatus` | Nêu rõ trạng thái của đối tượng nào |
| `flag` | `isVerified` hoặc `hasDiscount` | Diễn đạt ý nghĩa boolean |
| `value` | `totalAmount` hoặc `exchangeRate` | Tránh tên chung chung |
| `created` | `createdAt` | Thể hiện đây là thời điểm |

Ví dụ query root:

~~~graphql
type Query {
    user(id: ID!): User
    orders(customerId: ID!, first: Int = 20): OrderConnection!
}
~~~

Tên `user` và `orders` mô tả resource được trả về. Không cần thêm `get` hoặc `fetch` vì operation type `Query` đã thể hiện đây là thao tác đọc.

Mutation thường dùng động từ mô tả hành động nghiệp vụ:

~~~graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
    cancelOrder(orderId: ID!): CancelOrderPayload!
    confirmPayment(paymentId: ID!): Payment!
}
~~~

Tên mutation nên thể hiện kết quả nghiệp vụ. `cancelOrder` rõ hơn `updateOrderStatus` nếu use case thực sự là hủy đơn và có các quy tắc nghiệp vụ riêng.

## 4. Dùng danh từ số ít, số nhiều và tiền tố boolean nhất quán

Field trả về một object thường dùng danh từ số ít; field trả về collection thường dùng danh từ số nhiều:

~~~graphql
type User {
    address: Address
    orders: [Order!]!
    favoriteProduct: Product
    favoriteProducts: [Product!]!
}
~~~

Boolean field nên có tiền tố thể hiện câu hỏi mà giá trị trả lời:

~~~graphql
type Account {
    isActive: Boolean!
    hasVerifiedEmail: Boolean!
    canReceiveNotifications: Boolean!
}
~~~

Tên `active` hoặc `verified` vẫn hợp lệ về cú pháp, nhưng `isActive` và `hasVerifiedEmail` giúp client đọc điều kiện rõ ràng hơn. Chọn một quy ước rồi dùng nhất quán; đừng trộn `active`, `isLocked`, `verifiedEmail` và `hasAccess` nếu tất cả đều là boolean.

## 5. Tránh viết tắt và tên phụ thuộc công nghệ

Schema được nhiều client và ngôn ngữ sử dụng. Một tên viết tắt quen thuộc trong một nhóm có thể khó hiểu với nhóm khác.

~~~graphql
# Nên tránh
type Usr {
    usrId: ID!
    addr: String
    crtTs: String
    dbStatus: String
}

# Rõ nghĩa hơn
type User {
    id: ID!
    address: String
    createdAt: DateTime!
    accountStatus: AccountStatus!
}
~~~

Không đưa chi tiết triển khai như `db`, `sql`, `redis`, `row`, `table`, `cache` hoặc tên framework vào field công khai, trừ khi khái niệm đó thực sự thuộc domain. Client cần biết `accountStatus`, không cần biết dữ liệu đến từ cột `USR_STS` hay bảng `USER_MASTER`.

Các acronym rất phổ biến trong domain có thể giữ lại, nhưng phải thống nhất cách viết. Ví dụ `URL`, `SKU` hoặc `IP` nên được dùng theo convention đã chọn, thay vì mỗi nhóm tự tạo một kiểu.

## 6. Tên phải giữ nguyên ý nghĩa theo thời gian

Một tên ổn định không chỉ là chuỗi ký tự không đổi. Ý nghĩa và đơn vị của field cũng phải ổn định.

Ví dụ, nếu `createdAt` ban đầu có nghĩa là thời điểm tạo bản ghi, không được đổi nó thành thời điểm cập nhật gần nhất khi sản phẩm thay đổi:

~~~graphql
type Order {
    createdAt: DateTime!
    updatedAt: DateTime
}
~~~

Nếu cần thêm thời điểm cập nhật, thêm `updatedAt`. Không tái sử dụng `createdAt` cho ý nghĩa mới chỉ vì client đã quen với tên đó.

Các tên sau cần định nghĩa rõ trong schema description hoặc tài liệu domain:

- `amount`: số tiền trước hay sau thuế? Đơn vị tiền tệ nào?
- `price`: giá niêm yết, giá bán, giá sau giảm hay giá mỗi đơn vị?
- `duration`: đơn vị là milliseconds, seconds hay minutes?
- `date`: ngày lịch hay thời điểm có múi giờ?
- `status`: trạng thái của quy trình nào và có những giá trị nào?
- `count`: tổng số, số trang hiện tại hay số phần tử trong response?

Ví dụ thiết kế tiền tệ rõ ràng:

~~~graphql
type Money {
    amount: Decimal!
    currency: CurrencyCode!
}

type Product {
    unitPrice: Money!
}
~~~

Đặt tên và type theo domain giúp client không phải đoán đơn vị hoặc quy tắc diễn giải.

## 7. Tên field, argument và input field cũng là hợp đồng

Ổn định tên field mà bỏ qua tên argument vẫn có thể làm client hỏng.

~~~graphql
type Query {
    orders(customerId: ID!, first: Int = 20, after: String): OrderConnection!
}
~~~

Tên `customerId`, `first` và `after` cần được giữ ổn định. Đổi `customerId` thành `userId` là breaking change đối với operation đang gửi argument cũ.

Input object cũng có tên field công khai:

~~~graphql
input CreateOrderInput {
    productId: ID!
    quantity: Int!
    shippingAddress: AddressInput!
}
~~~

Không đổi `shippingAddress` thành `deliveryAddress` bằng cách xóa field cũ ngay. Hãy thêm field mới theo một giai đoạn tương thích nếu hai khái niệm có cùng semantics, hoặc thiết kế migration rõ ràng nếu semantics khác nhau.

Đặc biệt, thêm một argument bắt buộc hoặc input field non-null không có default có thể làm operation cũ không còn hợp lệ. Nếu muốn mở rộng input, ưu tiên field optional hoặc có default rồi xử lý trường hợp không được gửi.

## 8. Tên GraphQL không cần trùng tên Java method hoặc database column

GraphQL schema là contract độc lập với model nội bộ. Spring for GraphQL cho phép ánh xạ rõ type và field bằng `@SchemaMapping`.

SDL:

~~~graphql
type Query {
    user(id: ID!): User
}

type User {
    id: ID!
    fullName: String!
    emailAddress: String!
}
~~~

Java model có thể dùng cách đặt tên phù hợp với codebase:

~~~java
public record UserView(
        Long userId,
        String givenName,
        String familyName,
        String email
) {}
~~~

Resolver ánh xạ sang tên public của GraphQL:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class UserFieldController {

    @SchemaMapping(typeName = "User", field = "id")
    public String resolveId(UserView user) {
        return user.userId().toString();
    }

    @SchemaMapping(typeName = "User", field = "fullName")
    public String resolveFullName(UserView user) {
        return user.givenName() + " " + user.familyName();
    }

    @SchemaMapping(typeName = "User", field = "emailAddress")
    public String resolveEmailAddress(UserView user) {
        return user.email();
    }
}
~~~

Ở đây Java method tên `resolveFullName`, Java model có `givenName`/`familyName`, còn GraphQL field là `fullName`. Ba lớp không cần trùng tên vì mỗi lớp phục vụ một hợp đồng khác nhau.

Nếu bỏ `field` khỏi `@SchemaMapping`, Spring for GraphQL mặc định suy ra field name từ tên method. Cách đó ngắn gọn nhưng khiến đổi tên method có thể vô tình đổi mapping. Với field quan trọng hoặc public contract cần ổn định, khai báo `typeName` và `field` tường minh giúp việc refactor nội bộ an toàn hơn.

## 9. Đổi tên field bằng chiến lược add–deprecate–remove

Giả sử field `User.name` hiện tại không rõ đó là tên hiển thị, tên đầy đủ hay username. Domain thống nhất rằng field đúng phải là `fullName`.

Không đổi trực tiếp:

~~~graphql
# Breaking change: client cũ query name sẽ không validate được.
type User {
    id: ID!
    fullName: String!
}
~~~

Thay vào đó, thêm field mới và đánh dấu field cũ deprecated:

~~~graphql
type User {
    id: ID!
    fullName: String!
    name: String @deprecated(reason: "Use `fullName` instead.")
}
~~~

Trong giai đoạn chuyển đổi:

- Client mới query `fullName`.
- Client cũ tiếp tục query `name`.
- Cả hai field trả cùng một giá trị theo semantics đã công bố.
- Tooling có thể cảnh báo client không nên dùng field deprecated.
- Server theo dõi mức sử dụng field cũ trước khi lên kế hoạch xóa.

Chỉ xóa `name` khi đã xác nhận không còn client cần nó và quy trình phát hành cho phép breaking change.

## 10. @deprecated và deprecation reason

GraphQL có directive dựng sẵn `@deprecated` để đánh dấu field, argument, input field, enum value và directive definition đã lỗi thời. `reason` là chuỗi giải thích lý do và hướng thay thế.

Ví dụ:

~~~graphql
type User {
    fullName: String!
    name: String @deprecated(reason: "Use `fullName` instead.")
}

type Query {
    users(first: Int, limit: Int @deprecated(reason: "Use `first` instead.")): [User!]!
}

enum OrderStatus {
    PENDING
    CONFIRMED
    OLD_COMPLETED @deprecated(reason: "Use `COMPLETED` instead.")
    COMPLETED
}
~~~

Reason nên cụ thể và có hướng hành động:

| Reason kém hữu ích | Reason tốt hơn |
| --- | --- |
| `Deprecated` | Use `fullName` instead. |
| `Old field` | Use `unitPrice`, which includes currency. |
| `Do not use` | Use `orders(first:, after:)` for cursor pagination. |
| `Will be removed` | Use `emailAddress`; removal is planned after supported clients migrate. |

Deprecation không tự xóa field và cũng không tự ngăn client query field đó. Nó là metadata cho schema, documentation và tooling. Server vẫn cần giữ resolver và hành vi tương thích trong thời gian chuyển đổi.

Specification không cho phép deprecate argument hoặc input field đang là non-null và không có default. Nếu cần deprecate một input bắt buộc, trước tiên phải làm nó optional hoặc thêm default để client cũ vẫn gửi hợp lệ; sau đó mới gắn `@deprecated`.

## 11. Ánh xạ field cũ và mới về cùng logic trong Spring for GraphQL

Có thể giữ hai field trong SDL và cho cả hai resolver dùng chung một service hoặc một hàm chuyển đổi:

~~~graphql
type User {
    id: ID!
    fullName: String!
    name: String @deprecated(reason: "Use `fullName` instead.")
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class UserFieldController {

    @SchemaMapping(typeName = "User", field = "id")
    public String id(UserView user) {
        return user.userId().toString();
    }

    @SchemaMapping(typeName = "User", field = "fullName")
    public String fullName(UserView user) {
        return formatFullName(user);
    }

    @SchemaMapping(typeName = "User", field = "name")
    public String legacyName(UserView user) {
        return formatFullName(user);
    }

    private String formatFullName(UserView user) {
        return user.givenName() + " " + user.familyName();
    }
}
~~~

Hai mapping công khai có thể dùng cùng logic, tránh hai field dần trả kết quả khác nhau. Không cần đổi Java model hoặc database column chỉ để đổi tên field GraphQL.

Với query root, `@QueryMapping` ánh xạ method vào field dưới `Query`; method name mặc định được dùng làm field name nếu không khai báo mapping khác. Với nested field, `@SchemaMapping(typeName = ..., field = ...)` cho phép chỉ rõ public name. Chọn cách ánh xạ tường minh ở các field đang trong giai đoạn migration để tránh nhầm lẫn.

Nếu muốn tên Java method khác tên query field, có thể dùng `@SchemaMapping` tường minh ngay trên root type:

~~~java
@SchemaMapping(typeName = "Query", field = "user")
public UserView findUser(@Argument String id) {
    return userService.findById(id);
}
~~~

Ở đây method `findUser` vẫn resolve GraphQL field `Query.user`. Refactor tên method không làm đổi public schema.

## 12. GraphQL alias không thay thế schema migration

Client có thể dùng alias để đổi tên key trong response:

~~~graphql
query {
    displayName: name
}
~~~

Alias `displayName` chỉ thay đổi response key của operation đó. Server schema vẫn có field `name`; client khác không tự nhìn thấy field `displayName`. Alias không tạo field mới, không deprecate field cũ và không phải chiến lược rename ở cấp API.

Alias hữu ích khi một operation cần lấy cùng field nhiều lần với arguments khác nhau hoặc muốn đặt response key phù hợp với UI. Không dùng alias để thay thế việc tiến hóa schema công khai.

## 13. Các thay đổi tên và type có thể phá vỡ client

Khi review schema change, cần xem cả tên, type và semantics:

| Thay đổi | Rủi ro tương thích | Cách tiến hóa an toàn hơn |
| --- | --- | --- |
| Đổi tên field | Breaking: query cũ không validate | Thêm field mới, deprecate field cũ |
| Xóa field | Breaking với client đang query | Deprecate, đo usage, rồi mới xóa theo policy |
| Đổi tên argument | Breaking với operation gửi tên cũ | Thêm argument mới optional, deprecate argument cũ |
| Thêm argument optional | Thường additive | Giữ semantics và default rõ ràng |
| Thêm argument bắt buộc | Breaking với operation cũ | Dùng optional/default hoặc field mới |
| Đổi return type | Có thể breaking cho generated types và selection set | Thêm field mới có type mong muốn |
| Đổi nullable thành non-null hoặc ngược lại | Có thể thay đổi contract và generated client types | Giữ type cũ; thêm field mới nếu cần semantics khác |
| Thêm enum value | Có thể phá client dùng exhaustive switch | Hướng dẫn client xử lý unknown/future values |
| Đổi ý nghĩa field nhưng giữ nguyên tên/type | Breaking về semantics dù schema diff không phát hiện | Giữ nghĩa cũ và thêm field mới |
| Đổi đơn vị của field | Breaking về dữ liệu dù schema vẫn hợp lệ | Tạo field mới có tên/description thể hiện đơn vị |

Đặc biệt, đổi `String` thành `String!` có thể khiến execution phát sinh null propagation nếu resolver vẫn trả null; đổi `String!` thành `String` làm yếu đi bảo đảm mà client đang dựa vào. Không xem thay đổi nullability là refactor nội bộ.

## 14. Thêm field mới thường an toàn hơn đổi field hiện tại

Giả sử `Product.price` hiện chỉ là số decimal nhưng sản phẩm bắt đầu hỗ trợ nhiều currency. Không đổi ý nghĩa của `price` từ “số tiền” sang “Money object” bằng cách sửa type trực tiếp.

Có thể mở rộng schema:

~~~graphql
type Product {
    price: Decimal! @deprecated(reason: "Use `unitPrice` to read amount and currency.")
    unitPrice: Money!
}

type Money {
    amount: Decimal!
    currency: CurrencyCode!
}
~~~

Trong thời gian chuyển đổi, `price` giữ nguyên semantics cũ, ví dụ giá trị theo currency mặc định đã được hợp đồng quy định. `unitPrice` cung cấp biểu diễn đầy đủ mới. Nếu không thể xác định một semantics cũ ổn định cho `price`, cần mô tả rõ cách tương thích và thời điểm ngừng hỗ trợ.

## 15. Không tái sử dụng tên field đã deprecated

Field deprecated vẫn có thể được client sử dụng. Vì vậy, không được tái sử dụng tên đó cho một khái niệm khác trong thời gian field còn tồn tại.

Ví dụ `User.name` từng có nghĩa là full name. Không đổi resolver của `name` sang trả username chỉ vì domain hiện cần username. Thay vào đó:

~~~graphql
type User {
    fullName: String!
    username: String!
    name: String @deprecated(reason: "Use `fullName` instead.")
}
~~~

Giữ `name` trả full name đến hết thời gian tương thích. Nếu client muốn username, họ dùng `username`. Một tên cũ không được chuyển sang một ý nghĩa mới.

## 16. Theo dõi việc sử dụng field deprecated

Không nên xóa field chỉ vì đã thêm directive `@deprecated`. Trước khi xóa, cần biết client nào còn sử dụng field đó.

Một quy trình theo dõi có thể kết hợp:

- GraphQL operation/field usage telemetry ở router hoặc gateway.
- Persisted operation registry nếu hệ thống dùng persisted queries.
- Schema checks hoặc schema registry để phát hiện operation bị ảnh hưởng.
- Log/metrics đã chuẩn hóa, không lưu raw query hoặc dữ liệu nhạy cảm không cần thiết.
- Trao đổi với owner của các ứng dụng client đã đăng ký.

Nên thống kê theo client/operation đã được định danh có kiểm soát, environment và thời gian. Không đưa user ID hoặc raw query vào metric tags vì cardinality và privacy.

Nếu hệ thống chưa có field usage tracking, cần bổ sung cơ chế quan sát trước khi lên kế hoạch xóa field. Không có số liệu usage không đồng nghĩa field không còn được sử dụng.

## 17. Introspection giúp client nhận biết field deprecated

GraphQL introspection có thể trả `isDeprecated` và `deprecationReason` cho field. Dùng `includeDeprecated: true` để lấy cả field đã deprecated:

~~~graphql
query UserTypeDeprecations {
    __type(name: "User") {
        fields(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
~~~

Response có thể chứa:

~~~json
{
    "data": {
        "__type": {
            "fields": [
                {
                    "name": "fullName",
                    "isDeprecated": false,
                    "deprecationReason": null
                },
                {
                    "name": "name",
                    "isDeprecated": true,
                    "deprecationReason": "Use `fullName` instead."
                }
            ]
        }
    }
}
~~~

IDE, documentation generator và code generation tool có thể dùng metadata này để cảnh báo developer. Introspection không thay thế giao tiếp migration và cũng không chứng minh field cũ đã hết usage.

## 18. Kiểm thử contract cho tên field trong Spring for GraphQL

Nên kiểm tra cả hành vi field cũ/mới và metadata deprecation. Ví dụ một GraphQL slice test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.stereotype.Controller;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

interface UserService {
    UserView findById(String id);
}

@Controller
class UserQueryController {

    private final UserService userService;

    UserQueryController(UserService userService) {
        this.userService = userService;
    }

    @QueryMapping
    public UserView user(@Argument String id) {
        return userService.findById(id);
    }
}

@GraphQlTest({UserQueryController.class, UserFieldController.class})
class UserFieldContractTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    UserService userService;

    @Test
    void supportsNewAndDeprecatedFieldDuringMigration() {
        given(userService.findById("user-1")).willReturn(
                new UserView(1L, "Ada", "Lovelace", "ada@example.com")
        );

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    user(id: "user-1") {
                        fullName
                        name
                    }
                }
                """).execute();

        response.errors().verify();
        response.path("user.fullName")
                .entity(String.class)
                .isEqualTo("Ada Lovelace");

        response.path("user.name")
                .entity(String.class)
                .isEqualTo("Ada Lovelace");
    }

    @Test
    void exposesDeprecationReasonThroughIntrospection() {
        graphQlTester.document("""
                query {
                    __type(name: "User") {
                        fields(includeDeprecated: true) {
                            name
                            isDeprecated
                            deprecationReason
                        }
                    }
                }
                """)
                .execute()
                .path("__type.fields")
                .entityList(java.util.Map.class)
                .satisfies(fields -> {
                    java.util.Map<?, ?> legacyField = fields.stream()
                            .filter(field -> "name".equals(field.get("name")))
                            .findFirst()
                            .orElseThrow();
                    assertThat(legacyField.get("isDeprecated")).isEqualTo(true);
                    assertThat(legacyField.get("deprecationReason"))
                            .isEqualTo("Use `fullName` instead.");
                });
    }
}
~~~

Ví dụ tập trung minh họa hai hợp đồng cần kiểm tra. Trong test thực tế, cấu hình mock `UserService` hoặc fixture cho `user(id:)`, rồi assert cả `fullName` và `name` bằng cùng giá trị. Với introspection, test bind kết quả vào map để kiểm tra chính xác field `name` có `isDeprecated = true` và reason đúng. `@MockitoBean` có trong Spring Framework 6.2 trở lên; với dự án Spring Boot cũ hơn, dùng cơ chế mock bean tương ứng của phiên bản đó, chẳng hạn `@MockBean`.

Một số endpoint production có thể tắt introspection theo chính sách bảo mật. Khi đó, chạy contract test trên schema artifact hoặc test profile có introspection, không dựa vào việc introspection phải mở công khai ở production.

## 19. Schema change review trong CI/CD

Trước khi merge thay đổi schema, review cần trả lời:

1. Có field/argument/input field/enum value nào bị đổi tên hoặc xóa không?
2. Có thay đổi nullability, return type, default value hoặc semantics không?
3. Field mới có tên nhất quán với domain và các type khác không?
4. Field deprecated có reason chỉ rõ field thay thế không?
5. Resolver của field cũ và mới có giữ cùng semantics trong migration window không?
6. Client cũ có còn query được schema mới không?
7. Có test cho query cũ, query mới và introspection deprecation không?
8. Có theo dõi usage trước khi lên lịch xóa field không?

Có thể dùng schema diff/check trong CI để phát hiện breaking changes và lint naming convention. Schema diff không phát hiện được mọi thay đổi semantics; review nghiệp vụ và test vẫn cần thiết.

Ví dụ checklist thay đổi:

| Kiểm tra | Kết quả mong muốn |
| --- | --- |
| Thêm `fullName` | Schema diff ghi nhận field mới |
| Giữ `name` | Operation client cũ vẫn validate và chạy |
| Thêm `@deprecated` | Introspection trả `isDeprecated = true` và reason |
| Hai resolver | Trả cùng semantics trong giai đoạn migration |
| Usage tracking | Xác định client còn gọi `name` |
| Xóa `name` | Chỉ sau khi migration hoàn tất và change được phê duyệt là breaking |

## 20. Các anti-pattern khi đặt tên field

| Anti-pattern | Vì sao có vấn đề | Hướng xử lý |
| --- | --- | --- |
| Đổi tên field trực tiếp | Query cũ không còn hợp lệ | Add field mới, deprecate field cũ |
| Dùng tên theo database | Rò rỉ chi tiết triển khai và khó thay đổi storage | Dùng domain language |
| Dùng acronym tùy tiện | Client khó hiểu và thiếu nhất quán | Chỉ dùng acronym phổ biến đã thống nhất |
| Dùng `data`, `value`, `status` cho mọi thứ | Ý nghĩa không rõ trong ngữ cảnh | Dùng tên cụ thể như `paymentStatus` |
| Query field có `get`/`fetch` lẫn lộn | Schema không nhất quán | Dùng danh từ cho query, động từ cho mutation |
| Dùng singular cho list | Client phải đoán field trả object hay collection | Dùng plural noun cho collection |
| Tái sử dụng tên deprecated | Client cũ nhận dữ liệu mang nghĩa khác | Giữ semantics cũ đến khi field được xóa |
| Thêm required argument vào field đang dùng | Operation cũ thiếu argument sẽ lỗi | Thêm optional/default hoặc field mới |
| Đổi `createdAt` thành `updatedAt` nhưng giữ tên | Breaking về semantics mà schema diff khó phát hiện | Giữ field cũ, thêm field mới |
| Xóa field ngay sau khi deprecate | Client chưa kịp migration | Theo dõi usage và có thời gian chuyển đổi |
| Dùng alias như rename schema | Alias chỉ thay response key trong một operation | Tiến hóa schema bằng field mới |

## 21. Quy trình thiết kế và tiến hóa tên field

Khi thêm field mới hoặc muốn đổi tên một field hiện có:

1. Xác định khái niệm nghiệp vụ mà field đại diện.
2. Chọn tên `camelCase` cụ thể, nhất quán và không phụ thuộc database/framework.
3. Xác định rõ cardinality, nullability, đơn vị và semantics của dữ liệu.
4. Kiểm tra tên field/argument tương tự trong schema để tránh tạo nhiều cách gọi cho cùng một khái niệm.
5. Nếu cần rename, thêm field mới trước và giữ field cũ.
6. Đánh dấu field cũ bằng `@deprecated(reason: "Use ... instead.")`.
7. Ánh xạ field cũ và mới về cùng logic trong Spring controller/service.
8. Cập nhật documentation, generated clients và ví dụ query.
9. Kiểm thử cả query cũ, query mới và deprecation metadata.
10. Theo dõi usage của field cũ theo client/operation.
11. Thông báo migration và chỉ xóa field trong một thay đổi breaking đã được lên kế hoạch.
12. Không tái sử dụng tên field đã xóa cho một ý nghĩa khác nếu còn nguy cơ client cũ dựa vào nó.

GraphQL cho phép API tiến hóa mà không cần tạo version endpoint mới cho mọi thay đổi. Điều đó chỉ hiệu quả khi tên field và semantics được giữ ổn định, các thay đổi được bổ sung có kiểm soát và field cũ được deprecate đủ lâu để client chuyển đổi.

## Tài liệu tham khảo

- [GraphQL — Naming Conventions and Design Standards](https://www.graphql.org/learn/naming-design/)
- [GraphQL — Introduction: Evolve your API without versioning](https://graphql.org/learn/introduction/)
- [GraphQL Specification — Names and Field Deprecation](https://spec.graphql.org/September2026/)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Apollo GraphOS — Schema Naming Conventions](https://www.apollographql.com/docs/graphos/schema-design/guides/naming-conventions)
