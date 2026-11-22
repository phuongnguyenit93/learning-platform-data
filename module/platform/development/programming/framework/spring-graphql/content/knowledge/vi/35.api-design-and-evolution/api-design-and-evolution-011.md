# Mutation payload contract

Mutation là operation làm thay đổi trạng thái hoặc kích hoạt một hành động trong GraphQL API. Một mutation contract tốt cần mô tả rõ client gửi dữ liệu gì, kết quả thành công có gì, lỗi nghiệp vụ được trả ra sao và client có thể xử lý retry như thế nào.

Thay vì trả trực tiếp một entity, scalar hoặc boolean, nên thiết kế một payload type riêng cho từng mutation. Payload tạo một hợp đồng ổn định để sau này bổ sung `userErrors`, warning, metadata hoặc những object liên quan mà không phải đổi kiểu trả về của field mutation. Trong Spring for GraphQL, SDL định nghĩa payload contract, còn `@MutationMapping` nhận input, gọi application use case và chuyển kết quả thành payload.

## 1. Mutation biểu diễn hành động nghiệp vụ

Mutation nên mô tả một hành động có ý nghĩa với người dùng hoặc domain, ví dụ:

- `createOrder` — tạo đơn hàng.
- `cancelOrder` — hủy đơn hàng.
- `capturePayment` — ghi nhận thanh toán.
- `changeShippingAddress` — thay đổi địa chỉ giao hàng.
- `publishArticle` — xuất bản bài viết.

Tên mutation nên thể hiện hành động cụ thể. Một field chung chung như `updateEntity` hoặc `saveData` khó diễn đạt điều kiện nghiệp vụ, quyền truy cập và side effect mà client đang yêu cầu.

Hai quy ước tên phổ biến là verb-first (`createOrder`) và noun-first (`orderCreate`). Cả hai đều có thể sử dụng; điều quan trọng là chọn một quy ước và giữ nhất quán trong schema. Ví dụ dưới đây dùng verb-first.

## 2. Vì sao không nên trả trực tiếp entity hoặc boolean?

Một mutation đơn giản có thể trả trực tiếp entity:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): Order
}
```

Hoặc trả boolean:

```graphql
type Mutation {
    cancelOrder(id: ID!): Boolean!
}
```

Hai dạng này có thể dùng được trong API nhỏ, nhưng thiếu không gian để phát triển hợp đồng. Khi cần trả lỗi validation, warning, đối tượng liên quan hoặc metadata, phải thay đổi kiểu trả về và buộc client sửa operation.

Thay vào đó, trả một payload type riêng:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}
```

Client có thể chọn `order`, `userErrors` hoặc các field khác được bổ sung sau này. Payload tạo một điểm mở rộng ổn định cho mutation.

## 3. Dùng một input object riêng cho mỗi mutation

Nên gom dữ liệu đầu vào vào một input object có tên riêng và truyền qua argument `input`:

```graphql
input CreateOrderInput {
    customerId: ID!
    items: [OrderItemInput!]!
    idempotencyKey: String
}

input OrderItemInput {
    productId: ID!
    quantity: Int!
}

type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}
```

Cách này có một số lợi ích:

- Operation client chỉ cần một biến `$input`.
- Có thể thêm field tùy chọn vào input mà không thay đổi danh sách argument của mutation.
- Input type có tên riêng, dễ tái sử dụng trong tài liệu và code generation.
- Dễ phân biệt input của `CreateOrder` với input của `UpdateOrder` dù hai thao tác có vài field giống nhau.
- Hạn chế mutation có quá nhiều argument rời rạc.

Không nên dùng chung một input type khổng lồ cho mọi mutation chỉ vì chúng cùng thao tác trên `Order`. `CreateOrderInput`, `UpdateOrderInput` và `CancelOrderInput` thường có mục đích và quy tắc khác nhau.

## 4. Thiết kế payload type riêng cho mutation

Payload nên có tên cụ thể, thường kết thúc bằng `Payload`:

```graphql
type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type CancelOrderPayload {
    order: Order
    userErrors: [UserError!]!
}
```

Không nhất thiết mọi payload phải có cùng field. `CreateOrderPayload` có thể trả order vừa tạo; `CancelOrderPayload` có thể trả order sau khi hủy cùng thông tin refund; `CapturePaymentPayload` có thể trả payment transaction.

Nếu nhiều mutation thực sự có chung một kết quả và semantics giống nhau, có thể dùng một type chung. Tuy nhiên, đừng ép tất cả mutation vào `MutationPayload` chung với nhiều field nullable không liên quan. Payload riêng giúp schema dễ khám phá và tiến hóa hơn.

## 5. Hợp đồng thành công và lỗi nghiệp vụ

Một payload phổ biến có hai thành phần:

- Field kết quả nghiệp vụ, ví dụ `order`.
- Danh sách `userErrors` mô tả những điều kiện nghiệp vụ không được đáp ứng.

Quy ước:

| Kết quả | `order` | `userErrors` |
|---|---|---|
| Thành công | Có order | Danh sách rỗng. |
| Không đủ hàng | `null` | Có lỗi `INSUFFICIENT_STOCK`. |
| Sản phẩm không tồn tại | `null` | Có lỗi `PRODUCT_NOT_FOUND`. |
| Người dùng không được phép đặt hàng | `null` | Có lỗi theo chính sách API. |

Ví dụ response thành công:

```json
{
  "data": {
    "createOrder": {
      "order": {
        "id": "order-101",
        "status": "PLACED"
      },
      "userErrors": []
    }
  }
}
```

Ví dụ response có lỗi nghiệp vụ:

```json
{
  "data": {
    "createOrder": {
      "order": null,
      "userErrors": [
        {
          "code": "INSUFFICIENT_STOCK",
          "message": "Sản phẩm không đủ số lượng tồn kho",
          "inputPath": ["items", "0", "quantity"]
        }
      ]
    }
  }
}
```

Trong trường hợp thứ hai, mutation đã được thực thi bình thường theo GraphQL; nghiệp vụ từ chối thao tác và trả thông tin đó trong payload. Top-level `errors` không cần có phần tử cho một business rejection đã được mô hình hóa trong payload.

## 6. Định nghĩa `UserError` rõ ràng

SDL có thể khai báo:

```graphql
enum UserErrorCode {
    INVALID_INPUT
    INVALID_QUANTITY
    PRODUCT_NOT_FOUND
    PRODUCT_UNAVAILABLE
    INSUFFICIENT_STOCK
    CUSTOMER_NOT_ALLOWED
    IDEMPOTENCY_KEY_REUSED
    VERSION_CONFLICT
}

type UserError {
    code: UserErrorCode!
    message: String!
    inputPath: [String!]
}
```

Các field có ý nghĩa:

- `code`: mã ổn định để client phân nhánh xử lý.
- `message`: nội dung có thể hiển thị cho người dùng hoặc chuyển qua lớp localization của client.
- `inputPath`: đường dẫn tới phần input gây lỗi, nếu lỗi gắn với một field cụ thể.

Ví dụ `inputPath: ["items", "0", "quantity"]` chỉ ra phần tử đầu tiên trong `items`, field `quantity`. Với lỗi tổng thể không gắn một field cụ thể, `inputPath` có thể là `null`.

Không yêu cầu client phân tích chuỗi `message` để quyết định logic. Message có thể thay đổi cách diễn đạt hoặc ngôn ngữ; `code` mới là phần hợp đồng máy đọc được.

## 7. Phân biệt `inputPath` với GraphQL error `path`

Hai loại path này có ý nghĩa khác nhau:

| Path | Nằm ở đâu | Mô tả |
|---|---|---|
| `userErrors[].inputPath` | Trong mutation payload | Vị trí input do client gửi gây ra lỗi nghiệp vụ. |
| Top-level GraphQL `errors[].path` | Trong GraphQL response errors | Vị trí field trong response execution bị lỗi. |

Ví dụ `inputPath`:

```json
{
  "code": "INVALID_QUANTITY",
  "message": "Số lượng phải lớn hơn 0",
  "inputPath": ["items", "1", "quantity"]
}
```

Ví dụ top-level `path`:

```json
{
  "message": "Không thể tải thông tin khách hàng",
  "path": ["createOrder", "order", "customer"]
}
```

Client có thể dùng `inputPath` để đánh dấu field trong form. GraphQL `errors[].path` giúp xác định vị trí response field bị lỗi. Không dùng hai khái niệm thay thế cho nhau.

## 8. Phân biệt business error và GraphQL execution error

Không phải mọi lỗi đều nên đặt vào `userErrors`.

| Loại lỗi | Ví dụ | Cách biểu diễn phù hợp |
|---|---|---|
| GraphQL syntax/validation | Thiếu dấu ngoặc, chọn field không tồn tại | Top-level GraphQL `errors`. |
| Input coercion | Truyền chuỗi vào argument `Int!` | Top-level GraphQL `errors`; resolver chưa được gọi. |
| Binding/Bean Validation | Không bind được DTO hoặc constraint không hợp lệ | Theo chính sách API; thường là GraphQL error nếu không chuyển thành payload có chủ đích. |
| Business rejection | Không đủ hàng, đơn đã hủy, không đủ điều kiện | `userErrors` trong payload. |
| Authentication/authorization | Token không hợp lệ hoặc không được phép truy cập | Security/GraphQL error hoặc payload theo chính sách nhất quán của API. |
| System/infrastructure failure | Database mất kết nối, lỗi lập trình, dependency timeout | Top-level GraphQL execution error. |

Business rejection là một kết quả nghiệp vụ có thể dự đoán và client có thể xử lý. System failure là lỗi thực thi khiến server không hoàn thành resolver. Không nên bắt mọi exception rồi trả về `userErrors`, vì điều đó có thể che giấu sự cố và làm client hiểu nhầm rằng thao tác chỉ bị từ chối do input.

## 9. Chọn nullability cho payload

Một SDL thường dùng:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}
```

Lý do:

- `CreateOrderPayload!`: với các kết quả nghiệp vụ được xử lý bình thường, resolver luôn trả payload.
- `order: Order`: nullable vì không có order khi nghiệp vụ bị từ chối.
- `userErrors: [UserError!]!`: luôn có danh sách, rỗng khi thành công; mỗi phần tử lỗi không được null.

Không nên khai báo `order: Order!` nếu mutation có thể bị từ chối và không có order để trả. Nếu resolver trả null cho một field non-null, GraphQL tạo execution error và null lan lên parent nullable gần nhất.

## 10. Hiểu null propagation khi resolver gặp system error

Payload non-null không có nghĩa resolver không thể thất bại. Ví dụ `createOrder` trả `CreateOrderPayload!`, nhưng database ném exception. GraphQL ghi top-level error. Vì field mutation là non-null, null có thể lan lên root response data.

Nếu API có nhiều root mutation field trong cùng operation và muốn một field lỗi không làm mất dữ liệu của field mutation khác đã hoàn tất, có thể cân nhắc để root mutation field nullable:

```graphql
type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload
}
```

Khi đó execution error có thể làm riêng `createOrder` thành null và giữ các sibling field theo quy tắc propagation. Tuy nhiên, nhiều root mutation field vẫn không tự động thuộc cùng transaction. Việc chọn `Payload!` hay `Payload` phải dựa trên error isolation mong muốn và semantics của API, không chỉ theo một quy tắc máy móc.

## 11. Không trộn lỗi dự kiến với lỗi ngoài dự kiến

Một mutation có thể gặp hai nhóm tình huống:

**Business rejection:** sản phẩm hết hàng, số lượng không hợp lệ, trạng thái đơn hàng không cho phép hủy. Use case trả kết quả từ chối có cấu trúc; resolver chuyển thành `userErrors`.

**Execution failure:** database mất kết nối, lỗi lập trình, timeout không xử lý được. Exception đi qua cơ chế xử lý lỗi của Spring for GraphQL và trở thành top-level GraphQL error.

Đừng viết:

```java
try {
    return useCase.execute(command);
} catch (Exception ex) {
    return new CreateOrderPayload(null, List.of(
        new UserError("UNKNOWN", ex.getMessage(), null)
    ));
}
```

Đoạn code này biến mọi lỗi hệ thống thành lỗi input, đồng thời có nguy cơ lộ thông tin nội bộ qua `ex.getMessage()`.

## 12. Triển khai resolver chuyển application outcome thành payload

Định nghĩa input DTO:

```java
import java.util.List;

public record CreateOrderInput(
    String customerId,
    List<OrderItemInput> items,
    String idempotencyKey
) {}

public record OrderItemInput(String productId, int quantity) {}
```

Định nghĩa GraphQL response model:

```java
import java.util.List;

public record CreateOrderPayload(
    OrderView order,
    List<UserError> userErrors
) {
    public CreateOrderPayload {
        userErrors = List.copyOf(userErrors);
    }
}

public record UserError(
    UserErrorCode code,
    String message,
    List<String> inputPath
) {}

public enum UserErrorCode {
    INVALID_INPUT,
    INVALID_QUANTITY,
    PRODUCT_NOT_FOUND,
    PRODUCT_UNAVAILABLE,
    INSUFFICIENT_STOCK,
    CUSTOMER_NOT_ALLOWED,
    IDEMPOTENCY_KEY_REUSED,
    VERSION_CONFLICT
}
```

Application layer trả kết quả độc lập GraphQL:

```java
import java.util.List;
import java.util.Optional;

public record BusinessViolation(
    String code,
    String message,
    List<String> inputPath
) {}

public record CreateOrderOutcome(
    Optional<OrderSummary> order,
    List<BusinessViolation> violations
) {
    public static CreateOrderOutcome success(OrderSummary order) {
        return new CreateOrderOutcome(Optional.of(order), List.of());
    }

    public static CreateOrderOutcome rejected(List<BusinessViolation> violations) {
        return new CreateOrderOutcome(Optional.empty(), List.copyOf(violations));
    }
}
```

Resolver chỉ chuyển input thành command, gọi use case và ánh xạ kết quả:

```java
import java.security.Principal;
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
class OrderMutationController {

    private final CreateOrderUseCase createOrder;

    OrderMutationController(CreateOrderUseCase createOrder) {
        this.createOrder = createOrder;
    }

    @MutationMapping
    CreateOrderPayload createOrder(
            @Argument("input") CreateOrderInput input,
            Principal principal) {

        CreateOrderCommand command = new CreateOrderCommand(
            principal.getName(),
            input.customerId(),
            input.items().stream()
                .map(item -> new OrderLineCommand(item.productId(), item.quantity()))
                .toList(),
            input.idempotencyKey()
        );

        CreateOrderOutcome outcome = createOrder.execute(command);

        OrderView order = outcome.order()
            .map(OrderView::from)
            .orElse(null);

        List<UserError> userErrors = outcome.violations().stream()
            .map(this::toUserError)
            .toList();

        return new CreateOrderPayload(order, userErrors);
    }

    private UserError toUserError(BusinessViolation violation) {
        return new UserError(
            toUserErrorCode(violation.code()),
            violation.message(),
            violation.inputPath()
        );
    }

    private UserErrorCode toUserErrorCode(String code) {
        return switch (code) {
            case "INVALID_QUANTITY" -> UserErrorCode.INVALID_QUANTITY;
            case "PRODUCT_NOT_FOUND" -> UserErrorCode.PRODUCT_NOT_FOUND;
            case "PRODUCT_UNAVAILABLE" -> UserErrorCode.PRODUCT_UNAVAILABLE;
            case "INSUFFICIENT_STOCK" -> UserErrorCode.INSUFFICIENT_STOCK;
            case "CUSTOMER_NOT_ALLOWED" -> UserErrorCode.CUSTOMER_NOT_ALLOWED;
            case "IDEMPOTENCY_KEY_REUSED" -> UserErrorCode.IDEMPOTENCY_KEY_REUSED;
            case "VERSION_CONFLICT" -> UserErrorCode.VERSION_CONFLICT;
            case "INVALID_INPUT" -> UserErrorCode.INVALID_INPUT;
            default -> throw new IllegalStateException("Unsupported business error code");
        };
    }
}
```

Các kiểu application và view được resolver sử dụng:

```java
import java.util.List;

public record CreateOrderCommand(
    String actorId,
    String customerId,
    List<OrderLineCommand> lines,
    String idempotencyKey
) {}

public record OrderLineCommand(String productId, int quantity) {}

public record OrderSummary(String id, String status) {}

public interface CreateOrderUseCase {
    CreateOrderOutcome execute(CreateOrderCommand command);
}

public record OrderView(String id, String status) {
    public static OrderView from(OrderSummary summary) {
        return new OrderView(summary.id(), summary.status());
    }
}
```

Resolver ánh xạ application error code sang GraphQL enum một cách tường minh. Code không được hỗ trợ được xem là lỗi lập trình và đi qua execution error handling, thay vì âm thầm trả một mã khác.

## 13. Đặt business validation trong application/domain

Use case quyết định nghiệp vụ có được thực hiện hay không. Ví dụ, trước khi tạo order:

1. Xác minh customer thuộc phạm vi actor được phép thao tác.
2. Kiểm tra mỗi quantity lớn hơn 0.
3. Xác minh product tồn tại và còn bán.
4. Kiểm tra tồn kho.
5. Tính giá và áp dụng chính sách giảm giá.
6. Tạo order và lưu dữ liệu trong transaction.

Nếu điều kiện nghiệp vụ không đạt, use case có thể trả `CreateOrderOutcome.rejected(...)` với một hoặc nhiều `BusinessViolation`. Resolver chuyển chúng thành `UserError`.

Nếu từ chối xảy ra sau khi đã ghi dữ liệu, cần bảo đảm transaction không commit trạng thái dở dang. Có thể validate trước khi ghi, dùng transaction rollback phù hợp hoặc biểu diễn một trạng thái workflow có chủ đích. Không trả payload rejection sau khi đã để lại side effect ngoài hợp đồng.

## 14. Đặt tên và ổn định error code

Error code là một phần của API contract. Nên chọn mã:

- Ổn định qua các lần đổi message.
- Có ý nghĩa rõ ràng với client.
- Không phụ thuộc tên exception Java.
- Không chứa ID, email hoặc dữ liệu nhạy cảm.
- Có tài liệu giải thích cách client xử lý.

Ví dụ:

| Code | Ý nghĩa | Hướng xử lý phía client |
|---|---|---|
| `INVALID_QUANTITY` | Số lượng không hợp lệ | Hiển thị lỗi tại input quantity. |
| `PRODUCT_NOT_FOUND` | Không tìm thấy sản phẩm | Yêu cầu chọn lại sản phẩm. |
| `PRODUCT_UNAVAILABLE` | Sản phẩm không còn bán | Cập nhật giỏ hàng. |
| `INSUFFICIENT_STOCK` | Không đủ tồn kho | Cho phép giảm số lượng. |
| `CUSTOMER_NOT_ALLOWED` | Actor không được thao tác | Hiển thị thông báo quyền truy cập phù hợp. |
| `IDEMPOTENCY_KEY_REUSED` | Key được dùng cho payload khác | Tạo key mới hoặc kiểm tra request cũ. |
| `VERSION_CONFLICT` | Dữ liệu đã thay đổi | Tải lại dữ liệu mới nhất. |

Nếu dùng GraphQL enum cho code, việc bổ sung enum value có thể ảnh hưởng client xử lý exhaustive switch. Với API cần mã mở rộng thường xuyên, có thể cân nhắc `String!` cùng tài liệu mã lỗi và fallback ở client. Dù chọn enum hay string, không thay đổi ý nghĩa một code đã phát hành.

## 15. Phân biệt validation của GraphQL với validation nghiệp vụ

GraphQL tự kiểm tra một số điều kiện trước khi resolver chạy:

- Query có cú pháp hợp lệ không.
- Field có tồn tại trong schema không.
- Argument bắt buộc có được truyền không.
- Giá trị có chuyển được sang GraphQL scalar/input type không.
- Input object có chứa field không được khai báo không.

Ví dụ client truyền `quantity: "many"` trong khi schema khai báo `Int!`. GraphQL input coercion thất bại và resolver không được gọi. Đây là top-level GraphQL error.

Ngược lại, `quantity: 500` là một số nguyên hợp lệ về kiểu nhưng có thể vượt tồn kho. Đây là business validation và phù hợp với `userErrors`.

Spring for GraphQL cũng hỗ trợ Bean Validation với `@Valid` trên argument. Nếu constraint thất bại, `ConstraintViolationException` được ném. Ứng dụng cần quyết định rõ có ánh xạ lỗi đó thành top-level GraphQL error hay chuyển thành payload `userErrors`; không nên giả định mọi `@Valid` failure tự động được đưa vào payload.

## 16. Dùng `@GraphQlExceptionHandler` cho execution error

Các exception từ annotated controller có thể được xử lý bằng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice`.

Ví dụ ánh xạ lỗi hệ thống:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class GraphQlExecutionErrorHandler {

    @GraphQlExceptionHandler
    GraphQLError handle(
            UnexpectedOrderServiceException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Không thể xử lý yêu cầu lúc này")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
    }
}
```

`GraphqlErrorBuilder` được Spring chuẩn bị theo `DataFetchingEnvironment` hiện tại, giúp giữ thông tin path và vị trí phù hợp. Không đưa exception message hoặc stack trace nội bộ vào response.

Với DataFetcher không đến từ annotated controller, có thể dùng `DataFetcherExceptionResolver` và đăng ký resolver với `GraphQlSource`. Spring Boot starter tự phát hiện các bean `DataFetcherExceptionResolver`.

## 17. Có nên thêm `success: Boolean!` vào payload?

Một số API định nghĩa:

```graphql
type CreateOrderPayload {
    success: Boolean!
    order: Order
    userErrors: [UserError!]!
}
```

Field `success` thường dư thừa nếu contract đã quy định:

- Thành công: `order` có giá trị và `userErrors` rỗng.
- Business rejection: `order` null và `userErrors` có phần tử.

Nếu thêm `success`, server phải giữ ba field nhất quán trong mọi trường hợp. Chỉ thêm khi nó biểu đạt một trạng thái độc lập có ý nghĩa và client thực sự cần. Không dùng boolean để thay thế error code hoặc kết quả nghiệp vụ.

## 18. Có nên dùng union cho mutation result?

Một thiết kế khác là dùng union để biểu diễn các kết quả loại trừ nhau:

```graphql
union CreateOrderResult = Order | OrderRejected

type OrderRejected {
    userErrors: [UserError!]!
}

type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderResult!
}
```

Client phải dùng inline fragment theo concrete type:

```graphql
mutation CreateOrder($input: CreateOrderInput!) {
    createOrder(input: $input) {
        ... on Order {
            id
            status
        }
        ... on OrderRejected {
            userErrors {
                code
                message
                inputPath
            }
        }
    }
}
```

Union làm rõ kết quả là một trong nhiều biến thể, phù hợp khi mỗi outcome có cấu trúc rất khác nhau. Tuy nhiên, payload object thường dễ mở rộng hơn khi muốn trả thêm metadata hoặc object liên quan trên cả success và failure. Chọn một mô hình và giữ nhất quán giữa các mutation cùng nhóm.

## 19. `clientMutationId` có bắt buộc không?

Relay-style mutation thường truyền `clientMutationId` trong input và trả lại cùng giá trị trong payload:

```graphql
input CreateOrderInput {
    customerId: ID!
    clientMutationId: String
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
    clientMutationId: String
}
```

Field này giúp client tương quan response với lần submit, đặc biệt trong một số workflow optimistic UI hoặc Relay mutation. Nó không phải yêu cầu của GraphQL specification và không tự cung cấp idempotency.

Nếu client không dùng Relay hoặc không cần echo correlation value, không cần thêm field này chỉ vì một mẫu mutation cũ có nó. Nếu cần chống tạo trùng khi retry, dùng idempotency key có semantics phía server rõ ràng.

## 20. Idempotency cho mutation có side effect

Client có thể gửi lại mutation khi timeout hoặc mất kết nối mà không biết server đã xử lý thành công hay chưa. Với thao tác tạo order, capture payment hoặc đặt chỗ, retry mù quáng có thể tạo side effect trùng.

Có thể thêm `idempotencyKey` vào input:

```graphql
input CapturePaymentInput {
    orderId: ID!
    amount: Float!
    idempotencyKey: String!
}
```

Server nên định nghĩa rõ:

1. Key được scope theo actor/tenant và loại operation.
2. Key được lưu cùng fingerprint của input và kết quả xử lý.
3. Request retry cùng key và cùng nội dung trả lại kết quả đã ghi nhận.
4. Cùng key nhưng input khác phải bị từ chối bằng code ổn định như `IDEMPOTENCY_KEY_REUSED`.
5. Việc ghi key và trạng thái nghiệp vụ phải có tính nhất quán trong persistence layer.
6. Thời gian lưu key và chính sách retry phải được công bố.

Idempotency key không phải access token và không thay thế authorization. Với payment provider, nên truyền idempotency key phù hợp tới provider nếu API của họ hỗ trợ.

## 21. Concurrency và optimistic locking

Mutation cập nhật entity có thể đụng độ với một thay đổi khác. Input có thể mang `expectedVersion`:

```graphql
input UpdateOrderInput {
    id: ID!
    expectedVersion: Int!
    note: String
}
```

Nếu version hiện tại khác version client đã đọc, use case trả `VERSION_CONFLICT` trong payload. Client tải lại dữ liệu mới và quyết định có gửi lại thao tác hay không.

Không dùng `updatedAt` hoặc version chỉ để trang trí. Server phải kiểm tra điều kiện version trong transaction, thường bằng optimistic locking hoặc câu lệnh update có điều kiện. Nếu không, hai request đồng thời vẫn có thể ghi đè lẫn nhau.

## 22. Transaction và semantics của mutation

Payload mô tả kết quả API; nó không tự bảo đảm transaction. Application use case phải xác định thao tác nào cần atomicity.

Ví dụ tạo order có thể cần:

1. Xác minh customer và sản phẩm.
2. Kiểm tra tồn kho.
3. Tạo order và order lines.
4. Ghi reservation hoặc cập nhật tồn kho.
5. Lưu idempotency record.

Các thay đổi database cần atomic nên nằm trong một transaction của use case. Nếu business validation thất bại, không được để lại trạng thái dở dang.

Một GraphQL request có nhiều root mutation field được thực thi tuần tự, nhưng điều đó không tự động gom các resolver vào cùng một transaction. Nếu hai bước phải thành công hoặc rollback cùng nhau, tạo một mutation/use case bao trọn cả hai.

Không giữ database transaction mở trong lúc chờ một remote payment gateway lâu. Khi cần phối hợp nhiều hệ thống, cân nhắc outbox, saga, idempotency và compensation.

## 23. Dùng `ArgumentValue` cho partial update

Trong mutation cập nhật, cần phân biệt hai trạng thái:

- Client bỏ qua field: giữ nguyên giá trị hiện tại.
- Client gửi field với giá trị `null`: xóa giá trị hiện tại nếu contract cho phép.

Với `@Argument` thông thường, hai trường hợp có thể cùng được bind thành null. Spring for GraphQL cung cấp `ArgumentValue<T>` để biết argument bị omitted hay được truyền rõ ràng.

Ví dụ input DTO:

```java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateProductInput(
    String id,
    ArgumentValue<String> description
) {}
```

Use case có thể xử lý:

```java
if (input.description().isOmitted()) {
    // Không thay đổi description.
} else if (input.description().value() == null) {
    // Client yêu cầu xóa description.
} else {
    // Client gửi description mới.
}
```

SDL cần để field `description` nullable để client có thể gửi null:

```graphql
input UpdateProductInput {
    id: ID!
    description: String
}
```

`ArgumentValue` cũng được hỗ trợ ở field bên trong object argument. Hãy kiểm thử cả omitted, explicit null và giá trị cụ thể để contract patch không bị hiểu sai.

## 24. Thiết kế payload cho partial success

Không phải mutation nào cũng là all-or-nothing. Ví dụ import danh sách sản phẩm có thể chấp nhận một số dòng và từ chối các dòng khác. Nếu nghiệp vụ thực sự cho phép partial success, payload cần diễn đạt rõ kết quả từng phần:

```graphql
type ImportProductsPayload {
    imported: [Product!]!
    rejected: [RejectedProduct!]!
    userErrors: [UserError!]!
}

type RejectedProduct {
    rowNumber: Int!
    inputPath: [String!]
    code: String!
    message: String!
}
```

Contract phải nói rõ mỗi dòng có transaction riêng hay toàn bộ import là atomic. Không trả một `success: true` khi chỉ một phần dữ liệu được ghi nếu client không có cách biết phần nào thành công.

Với mutation tạo một resource đơn lẻ như `createOrder`, thường nên giữ semantics đơn giản: tạo hoàn chỉnh hoặc trả business errors mà không để lại order dở dang.

## 25. Kiểm thử payload thành công bằng `GraphQlTester`

Thêm dependency test:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Operation có thể được viết với variables:

```graphql
mutation CreateOrder($input: CreateOrderInput!) {
    createOrder(input: $input) {
        order {
            id
            status
        }
        userErrors {
            code
            message
            inputPath
        }
    }
}
```

Test thành công nên kiểm tra order có dữ liệu và `userErrors` rỗng:

```java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;

@GraphQlTest(OrderMutationController.class)
@Import(GraphQlExecutionErrorHandler.class)
@WithMockUser(username = "alice")
class CreateOrderMutationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    CreateOrderUseCase createOrder;

    private static final String CREATE_ORDER_DOCUMENT = """
        mutation CreateOrder($input: CreateOrderInput!) {
            createOrder(input: $input) {
                order { id status }
                userErrors { code message inputPath }
            }
        }
        """;

    private Map<String, Object> input(int quantity) {
        return Map.of(
            "customerId", "customer-1",
            "items", List.of(Map.of(
                "productId", "product-1",
                "quantity", quantity
            ))
        );
    }

    @Test
    void returnsOrderAndEmptyUserErrorsOnSuccess() {
        given(createOrder.execute(any(CreateOrderCommand.class)))
            .willReturn(CreateOrderOutcome.success(
                new OrderSummary("order-101", "PLACED")
            ));

        GraphQlTester.Response response = graphQlTester.document(CREATE_ORDER_DOCUMENT)
            .variable("input", input(2))
            .executeAndVerify();

        response.path("createOrder.order.id")
            .entity(String.class)
            .isEqualTo("order-101");

        response.path("createOrder.userErrors")
            .entityList(UserError.class)
            .hasSize(0);
    }
}
```

Ví dụ dùng `@GraphQlTest` của Spring Boot 3.x và `@MockitoBean` của Spring Framework 6.2 trở lên. `@WithMockUser` cung cấp principal cho resolver; dependency `spring-security-test` chỉ cần khi test có Spring Security. `executeAndVerify()` xác minh response không có top-level GraphQL errors, còn hai assertion trên cùng một `Response` kiểm tra kết quả và danh sách lỗi nghiệp vụ.

Với Spring Boot 4.x, package của `@GraphQlTest` chuyển sang `org.springframework.boot.graphql.test.autoconfigure`. `@MockitoBean` thuộc Spring Framework 6.2 trở lên; nếu dự án cũ hơn, dùng mock bean annotation tương ứng phiên bản Spring Boot.

## 26. Kiểm thử business rejection trong payload

Với business rejection, GraphQL execution vẫn thành công nên không gọi `errors().verify()` để mong top-level error. Hãy kiểm tra payload:

```java
@Test
void returnsUserErrorWhenStockIsInsufficient() {
    given(createOrder.execute(any(CreateOrderCommand.class)))
        .willReturn(CreateOrderOutcome.rejected(List.of(
            new BusinessViolation(
                "INSUFFICIENT_STOCK",
                "Sản phẩm không đủ số lượng tồn kho",
                List.of("items", "0", "quantity")
            )
        )));

    GraphQlTester.Response response = graphQlTester.document(CREATE_ORDER_DOCUMENT)
        .variable("input", input(200))
        .executeAndVerify();

    response.path("createOrder.order").valueIsNull();
    response.path("createOrder.userErrors[0].code")
        .entity(String.class)
        .isEqualTo("INSUFFICIENT_STOCK");
}
```

Đây là method tiếp nối trong `CreateOrderMutationTests` ở phần trước. Nó thực thi mutation một lần rồi kiểm tra cả hai path trên cùng response. Business rejection không tạo top-level GraphQL error nên `executeAndVerify()` vẫn phù hợp.

## 27. Kiểm thử top-level execution error riêng biệt

Khi use case ném lỗi hệ thống, test phải xác minh top-level GraphQL error và không để lộ message nội bộ:

```java
@Test
void reportsUnexpectedFailureAsGraphQlError() {
    given(createOrder.execute(any(CreateOrderCommand.class)))
        .willThrow(new UnexpectedOrderServiceException("database details"));

    GraphQlTester.Response response = graphQlTester.document(CREATE_ORDER_DOCUMENT)
        .variable("input", input(2))
        .execute();

    response.errors()
        .expect(error -> error.getMessage().equals("Không thể xử lý yêu cầu lúc này"))
        .verify();
}
```

Đây là method tiếp nối trong `CreateOrderMutationTests` ở phần trước. Class đã import `GraphQlExecutionErrorHandler` để test slice sử dụng exception mapping. Test kiểm tra ranh giới giữa business `userErrors` và execution errors. Nếu schema khai báo mutation payload non-null, lỗi execution có thể làm `data` bị null do non-null propagation; test không nên giả định payload vẫn tồn tại sau system failure.

## 28. Kiểm thử contract cho client cũ

Khi payload được mở rộng, operation cũ vẫn nên chạy:

- Nếu thêm `warnings`, client cũ không chọn field này vẫn hợp lệ.
- Nếu thêm `payment`, client cũ vẫn có thể chỉ chọn `order` và `userErrors`.
- Nếu thêm `clientMutationId`, operation cũ không yêu cầu field đó vẫn hoạt động.
- Nếu thêm một input field tùy chọn, input cũ vẫn hợp lệ.

Lưu các mutation operation đại diện trong test resource hoặc persisted operation registry để CI có thể thực thi lại sau mỗi schema change. Kiểm tra schema diff và runtime behavior; chỉ kiểm tra SDL không chứng minh resolver trả payload đúng.

## 29. Mở rộng payload mà không phá client

Payload type riêng cho phép bổ sung field mới theo hướng additive:

```graphql
type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
    warnings: [MutationWarning!]!
    replayed: Boolean
}

type MutationWarning {
    code: String!
    message: String!
}
```

Client cũ chỉ chọn `order` và `userErrors` vẫn hợp lệ. Client mới có thể chọn `warnings` hoặc `replayed`.

Khi thêm field payload:

- Giữ nguyên semantics của field cũ.
- Dùng nullable nếu dữ liệu không luôn có sẵn.
- Nếu field list luôn có thể trả danh sách rỗng, dùng `[Type!]!` và bảo đảm resolver luôn trả list.
- Không đổi `userErrors` từ lỗi nghiệp vụ sang lỗi hệ thống.
- Không thay đổi code đã phát hành để mang nghĩa khác.
- Kiểm tra performance nếu field mới gọi thêm service hoặc database.

## 30. Authorization và thông tin nhạy cảm trong payload

Mutation payload là dữ liệu trả về cho client, vì vậy không đưa thông tin nội bộ vào `userErrors`:

- Không trả SQL, stack trace hoặc tên class exception nội bộ.
- Không trả thông tin tồn kho nhạy cảm nếu người dùng không được phép xem.
- Không trả dữ liệu customer hoặc payment ngoài phạm vi quyền.
- Không dùng `message` để tiết lộ resource có tồn tại hay không nếu chính sách bảo mật cần che giấu điều đó.
- Không coi `customerId` trong input là bằng chứng user được quyền thao tác customer đó.

Resolver có thể lấy `Principal` từ Spring Security và truyền actor ID vào use case. Application layer kiểm tra quyền trên resource cụ thể. Nếu muốn trả business rejection cho trường hợp không đủ quyền, cần thống nhất cách đó với chính sách security của toàn API; nhiều hệ thống vẫn dùng top-level `FORBIDDEN` cho authorization failure.

## 31. Những lỗi thường gặp khi thiết kế mutation payload

**Trả entity trực tiếp rồi mới phát hiện cần thêm errors.** Thay kiểu trả về sẽ buộc client sửa operation. Dùng payload type riêng từ đầu.

**Trả boolean cho mọi mutation.** Client không biết lỗi cụ thể hoặc trạng thái resource sau thao tác. Trả object payload có kết quả và error details.

**Dùng một payload chung quá rộng.** Nhiều field nullable không liên quan làm schema khó hiểu. Tạo payload riêng theo hành động nghiệp vụ.

**Dùng `userErrors` cho lỗi hệ thống.** Database outage không phải lỗi input. Để execution error đi qua GraphQL error handling.

**Đưa logic client vào `message`.** Message thay đổi theo ngôn ngữ và cách diễn đạt. Dùng `code` ổn định cho logic.

**Để `userErrors` nullable hoặc chứa item null.** Client phải xử lý quá nhiều trạng thái. Thường dùng `[UserError!]!` và trả list rỗng khi thành công.

**Để field kết quả non-null khi business rejection không có kết quả.** Non-null propagation có thể làm mất payload. Dùng nullable result field như `order: Order`.

**Thêm required input field hoặc argument vào mutation hiện có.** Client cũ có thể không còn hợp lệ. Bắt đầu bằng input field optional hoặc có default.

**Coi `clientMutationId` là idempotency key.** Echo correlation ID không tự chống thực thi trùng. Cần idempotency storage và semantics phía server.

**Thực thi mutation hai lần trong một test để kiểm tra hai path.** Có thể tạo side effect trùng. Giữ một response và assert nhiều path.

**Dùng enum error code mà không có chiến lược unknown value.** Client exhaustive switch có thể không xử lý code mới. Cân nhắc string code hoặc fallback.

## 32. Checklist thiết kế mutation contract

- [ ] Tên mutation mô tả hành động nghiệp vụ rõ ràng.
- [ ] Mutation có input object type riêng và argument `input`.
- [ ] Mutation trả payload type riêng, có thể tiến hóa.
- [ ] Field kết quả nullable nếu business rejection không tạo ra kết quả.
- [ ] `userErrors` luôn có list, rỗng khi thành công.
- [ ] Error code ổn định, message không được dùng làm machine contract.
- [ ] `inputPath` được phân biệt với top-level GraphQL error path.
- [ ] Business rejection được phân biệt với validation/coercion và system error.
- [ ] Resolver gọi application use case, không tự thực thi quy tắc nghiệp vụ.
- [ ] Transaction bao phủ đúng một use case cần atomicity.
- [ ] Mutation có side effect hỗ trợ idempotency khi cần retry an toàn.
- [ ] Update mutation phân biệt omitted và explicit null khi cần.
- [ ] Authorization và tenant ownership được kiểm tra ở server.
- [ ] GraphQlTester kiểm tra success, business rejection và execution error.
- [ ] Contract test xác minh operation cũ vẫn hoạt động sau khi payload mở rộng.

## Kết luận

Mutation payload là hợp đồng giữa client và nghiệp vụ phía server. Hãy dùng input object riêng, payload type riêng và field kết quả phù hợp với khả năng thành công/thất bại. Đưa business rejection vào `userErrors` với code ổn định và input path rõ ràng; giữ GraphQL syntax/coercion và system execution failures trong top-level `errors`. Trong Spring for GraphQL, `@MutationMapping` nên chuyển input thành command, gọi application use case rồi ánh xạ outcome thành payload. Kiểm thử cả success, business rejection và execution error bằng `GraphQlTester`, đồng thời thiết kế idempotency, concurrency và transaction theo side effect thực tế.

## Tài liệu tham khảo

- [GraphQL — Naming Conventions and Design Standards](https://www.graphql.org/learn/naming-design/)
- [GraphQL — Schema Design](https://graphql.org/learn/schema-design/)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Testing with GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Apollo — Designing GraphQL Mutations](https://www.apollographql.com/blog/designing-graphql-mutations)
- [Shopify — GraphQL API Design Tutorial](https://github.com/Shopify/graphql-design-tutorial/blob/master/TUTORIAL.md)
