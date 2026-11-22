# Error classification trong GraphQL và Spring for GraphQL

GraphQL có nhiều loại lỗi xuất hiện ở những giai đoạn khác nhau của một operation. Một request có thể sai cú pháp nên không được thực thi; một field resolver có thể ném exception trong khi các field khác vẫn trả dữ liệu; hoặc mutation có thể hoàn tất đúng về mặt GraphQL nhưng thất bại theo quy tắc nghiệp vụ, chẳng hạn email đã được sử dụng.

Phân loại lỗi giúp server chọn đúng cách phản hồi và giúp client biết phải làm gì tiếp theo. Trong Spring for GraphQL, cần phân biệt lỗi request, lỗi execution và lỗi nghiệp vụ; sau đó dùng GraphQL error classification, exception resolver hoặc payload có kiểu để biểu diễn từng trường hợp.

## 1. Ba nhóm lỗi thường gặp

Ở góc độ thiết kế API, có thể chia các tình huống thành ba nhóm:

| Nhóm | Thời điểm | Resolver có chạy không? | Cách biểu diễn phổ biến |
|---|---|---|---|
| Request error | Parse, validate, chọn operation hoặc coercion variables thất bại | Không | Top-level `errors`; request không được thực thi. |
| Execution error | Field resolver hoặc bước hoàn thiện giá trị phát sinh lỗi | Có thể đã chạy một phần | `data` cùng `errors`; field lỗi thường thành `null`, có thể có partial data. |
| Business error | Quy tắc nghiệp vụ từ chối một hành động hợp lệ về mặt GraphQL | Có | Payload trong `data`, ví dụ `userErrors` hoặc kiểu kết quả riêng. |

Đây là cách phân loại hữu ích khi thiết kế API. GraphQL specification định nghĩa request errors và execution errors; business error là quy ước của ứng dụng, thường được biểu diễn trong schema để client có thể xử lý như một kết quả nghiệp vụ.

Ví dụ:

- `query { unknownField }`: request error vì field không tồn tại trong schema.
- Resolver gọi database nhưng kết nối thất bại: execution error.
- `createUser` nhận dữ liệu đúng kiểu nhưng email đã được đăng ký: business error có thể trả trong payload.

## 2. Request errors: lỗi trước khi thực thi

Request error xuất hiện trước khi GraphQL bắt đầu thực thi các field. Các trường hợp phổ biến:

**Syntax/parse error:** document không phải cú pháp GraphQL hợp lệ, ví dụ thiếu dấu ngoặc hoặc dấu nháy.

```graphql
query {
    bookById(id: "book-01") {
        id
        title
    # thiếu dấu đóng ngoặc
```

**Validation error:** document parse được nhưng không hợp lệ với schema, ví dụ gọi field không tồn tại hoặc chọn subfield trên scalar.

```graphql
query {
    bookById(id: "book-01") {
        unknownProperty
    }
}
```

**Variable coercion error:** biến không phù hợp kiểu khai báo, thiếu biến Non-null hoặc giá trị không thể chuyển đổi sang kiểu GraphQL.

```graphql
query FindBook($id: ID!) {
    bookById(id: $id) {
        id
    }
}
```

Nếu client không cung cấp `$id`, request không vượt qua bước coercion vì biến được khai báo Non-null.

**Operation selection error:** document chứa nhiều operation nhưng client không chỉ định operation name cần chạy, hoặc tên được chọn không tồn tại.

Với các lỗi này, GraphQL không gọi `@QueryMapping`, `@MutationMapping` hay `@SchemaMapping`. Theo request-error response format, response có danh sách `errors` và không có entry `data`, vì execution chưa bắt đầu. Client cần sửa document, variables hoặc operation name. Vì resolver chưa chạy, `DataFetcherExceptionResolver` và `@GraphQlExceptionHandler` không phải nơi xử lý các lỗi parse/validation này.

## 3. Execution errors: lỗi trong quá trình thực thi

Execution error xảy ra sau khi GraphQL chấp nhận document và bắt đầu phân giải field. Nguyên nhân có thể gồm:

- Data fetcher hoặc controller ném exception.
- Database, HTTP service hoặc hệ thống phụ thuộc gặp sự cố.
- Custom scalar không serialize được giá trị trả về.
- Resolver trả `null` cho field được khai báo Non-null.
- Giá trị trả về không phù hợp kiểu GraphQL khi hoàn thiện response.
- Một field con phát sinh lỗi trong khi các field khác đã phân giải thành công.

Ví dụ query:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
        author {
            name
        }
    }
}
```

Giả sử `Book.id` và `Book.title` phân giải thành công nhưng resolver `Book.author` ném exception. Nếu `author` là nullable, response có thể chứa:

```json
{
  "data": {
    "bookById": {
      "id": "book-01",
      "title": "GraphQL Basics",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["bookById", "author"]
    }
  ]
}
```

Client vẫn nhận được dữ liệu của những field đã thành công. Vì vậy, không nên coi sự xuất hiện của `errors` đồng nghĩa toàn bộ operation không có dữ liệu.

## 4. Đọc cấu trúc GraphQL error

Một phần tử trong danh sách `errors` có thể có các thuộc tính sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| `message` | Mô tả lỗi để client hoặc developer hiểu tình huống. |
| `locations` | Vị trí trong GraphQL document, gồm line và column, nếu xác định được. |
| `path` | Đường dẫn tới field trong response gây ra execution error. |
| `extensions` | Metadata bổ sung như mã lỗi, loại lỗi hoặc thông tin tracing. |

Ví dụ response:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book not found",
      "locations": [
        { "line": 2, "column": 5 }
      ],
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

`locations` trỏ đến vị trí trong document mà client gửi, không phải số dòng trong file SDL hay source Java. `path` dùng response key; nếu query đặt alias, path chứa alias đó. Với list, path còn có chỉ số phần tử.

Ví dụ query có alias và list:

```graphql
query {
    featured: books {
        title
        author {
            name
        }
    }
}
```

Nếu author của phần tử thứ hai lỗi, path có thể có dạng `["featured", 1, "author"]`. Client có thể dùng path để xác định chính xác phần nào của response bị lỗi.

Request errors thường không có `path`, vì chưa có field nào được thực thi. `locations` có thể vẫn có nếu parser hoặc validator xác định được vị trí lỗi trong document.

## 5. `data` và `errors`: partial data và null propagation

GraphQL response có quy tắc quan trọng: lỗi ở một field không nhất thiết làm mất toàn bộ `data`. Khi field resolver lỗi, field đó thường nhận `null` và error được thêm vào danh sách `errors`.

Tuy nhiên, nullability trong SDL quyết định lỗi lan truyền đến đâu.

```graphql
type Book {
    id: ID!
    author: Author
}
```

Nếu `author` lỗi, `author` trở thành `null`, nhưng `Book` vẫn có thể được trả về.

Nếu schema đổi thành:

```graphql
type Book {
    id: ID!
    author: Author!
}
```

thì `author` không được phép là `null`. Lỗi tại field này lan truyền lên parent `Book`; nếu field cha `bookById` nullable, toàn bộ `bookById` trở thành `null`. Nếu các parent tiếp theo cũng Non-null, lỗi tiếp tục lan lên cho tới nullable boundary gần nhất. Trong trường hợp tất cả đường lên root đều Non-null, `data` có thể là `null`.

Khi thiết kế schema, hãy quyết định rõ field nào thật sự luôn có dữ liệu. Đừng dùng `!` chỉ để thể hiện mong muốn; Non-null là cam kết mà resolver phải bảo đảm trong mọi tình huống hợp lệ.

## 6. Error classification trong Spring for GraphQL

Spring for GraphQL cung cấp `ErrorType`, một enum triển khai `ErrorClassification`, để phân loại các lỗi thường gặp khi server tạo `GraphQLError`:

| `ErrorType` | Ý nghĩa thường dùng |
|---|---|
| `BAD_REQUEST` | Request hoặc dữ liệu đầu vào không được chấp nhận ở tầng xử lý của ứng dụng. |
| `UNAUTHORIZED` | Request chưa được xác thực hoặc credentials không hợp lệ. |
| `FORBIDDEN` | Người dùng đã xác thực nhưng không có quyền thực hiện thao tác. |
| `NOT_FOUND` | Tài nguyên được yêu cầu không tồn tại. |
| `INTERNAL_ERROR` | Lỗi nội bộ không thuộc nhóm cụ thể hơn. |

Các giá trị này giúp chuẩn hóa nhóm lỗi do ứng dụng tạo ra. Chúng không thay thế mã lỗi nghiệp vụ riêng và cũng không phải danh sách phân loại duy nhất được GraphQL Java dùng cho parse/validation. Những lỗi phát sinh trước execution có thể mang classification riêng của GraphQL Java; `ErrorType` của Spring thường được dùng khi ứng dụng chủ động tạo `GraphQLError`, chẳng hạn trong exception resolver. Nhiều lỗi khác nhau có thể cùng thuộc `BAD_REQUEST`, nhưng client vẫn cần phân biệt `DUPLICATE_EMAIL`, `INVALID_STATE` hoặc `INVALID_COUPON`.

Có thể tạo GraphQL error với `GraphqlErrorBuilder`:

```java
GraphQLError error = GraphqlErrorBuilder.newError(environment)
    .errorType(ErrorType.NOT_FOUND)
    .message("Book not found")
    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
    .build();
```

Trong ví dụ, `ErrorType.NOT_FOUND` phân loại lỗi ở mức tổng quát; `extensions.code` là mã ổn định do ứng dụng quy định. Client nên dựa vào mã được tài liệu hóa để xử lý, thay vì phân tích nội dung `message`.

## 7. Ánh xạ exception thành GraphQL errors

Với exception phát sinh từ resolver, Spring for GraphQL cung cấp hai cách thường dùng:

- `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice`.
- `DataFetcherExceptionResolver` hoặc lớp tiện ích `DataFetcherExceptionResolverAdapter` để xử lý tập trung.

Ví dụ exception nghiệp vụ:

```java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
```

Handler tập trung:

```java
@ControllerAdvice
class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

`DataFetchingEnvironment` giúp error builder gắn thông tin liên quan tới vị trí thực thi và response path. Cách này phù hợp với exception do data fetcher ném ra.

Không nên dùng exception handler để chuyển mọi lỗi thành cùng một mã `INTERNAL_ERROR`. Hãy phân biệt lỗi có thể dự đoán và lỗi không mong đợi; chỉ công bố thông tin an toàn cho client, còn stack trace và chi tiết hệ thống cần được ghi log phía server.

## 8. Request errors và execution errors cần xử lý ở lớp khác nhau

Không phải mọi GraphQL error đều đi qua exception resolver:

| Giai đoạn | Ví dụ | Cơ chế xử lý phù hợp |
|---|---|---|
| Parse | Document sai cú pháp | GraphQL parser; client sửa document. |
| Validation | Field không tồn tại, selection set sai | GraphQL validator; client sửa query theo schema. |
| Variable coercion | Thiếu biến Non-null hoặc sai kiểu | GraphQL input coercion; client sửa variables. |
| Data fetching | Resolver ném exception | `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`. |
| Value completion | Scalar serialization lỗi, Non-null nhận `null` | GraphQL execution; kiểm tra kiểu trả về và nullability. |
| Business validation | Email trùng, trạng thái không cho phép | Payload có `userErrors` hoặc kiểu kết quả nghiệp vụ. |

Request errors xảy ra trước khi data fetcher được gọi. Vì vậy, nếu client gửi một field không có trong schema, không có `@QueryMapping` nào để bắt lỗi đó. Tương tự, nếu variable không thể coercion, resolver mutation không chạy.

Khi cần quan sát request errors ở cấp transport, có thể dùng `WebGraphQlInterceptor` để đọc errors trong response sau khi GraphQL xử lý request. Đây là điểm quan sát response, không phải cách thay thế parser hoặc validator.

## 9. Business errors: lỗi nghiệp vụ trong `data`

Một business error là kết quả nghiệp vụ dự kiến, không nhất thiết là lỗi thực thi GraphQL. Ví dụ tạo tài khoản với email đã tồn tại: document và variables đều hợp lệ, server thực thi mutation đúng, nhưng quy tắc nghiệp vụ từ chối thao tác.

Có thể định nghĩa payload:

```graphql
input RegisterUserInput {
    email: String!
    name: String!
}

type User {
    id: ID!
    email: String!
    name: String!
}

type Mutation {
    registerUser(input: RegisterUserInput!): RegisterUserPayload!
}

type RegisterUserPayload {
    user: User
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: [String!]
}
```

Java có thể biểu diễn payload bằng record:

```java
public record UserError(String code, String message, List<String> field) {}

public record RegisterUserPayload(User user, List<UserError> userErrors) {}
```

Resolver trả payload:

```java
@MutationMapping
RegisterUserPayload registerUser(@Argument("input") RegisterUserInput input) {
    if (userService.emailExists(input.email())) {
        return new RegisterUserPayload(
            null,
            List.of(new UserError(
                "DUPLICATE_EMAIL",
                "Email đã được sử dụng",
                List.of("input", "email")
            ))
        );
    }

    User user = userService.register(input);
    return new RegisterUserPayload(user, List.of());
}
```

Khi email trùng, response vẫn có `data.registerUser.userErrors`; không cần top-level `errors` nếu đây là kết quả dự kiến theo hợp đồng API.

Client có thể hiển thị message bên cạnh field tương ứng, cho phép người dùng sửa và gửi lại. Nếu dùng top-level execution error cho mọi business validation, client sẽ khó phân biệt lỗi có thể khắc phục với lỗi hệ thống.

Không có quy tắc bắt buộc rằng mọi business error phải nằm trong payload. Điều quan trọng là chọn hợp đồng nhất quán: trạng thái nghiệp vụ dự kiến thường nên có kiểu kết quả rõ ràng; exception hoặc lỗi không mong đợi nên nằm trong top-level `errors`.

## 10. Authentication và authorization errors

Lỗi xác thực và phân quyền có thể xuất hiện ở nhiều tầng:

- Nếu Spring Security filter chain từ chối HTTP request trước GraphQL handler, client thường nhận HTTP `401` hoặc `403` theo cấu hình security entry point/access denied handler; không nhất thiết có GraphQL response.
- Nếu request tới GraphQL và một resolver/service từ chối quyền, exception có thể được ánh xạ thành GraphQL error với `UNAUTHORIZED` hoặc `FORBIDDEN`.
- Nếu API biểu diễn quyền truy cập như một kết quả nghiệp vụ có thể xử lý, payload có thể chứa mã lỗi riêng, nhưng không được làm lộ tài nguyên mà người dùng không có quyền biết.

Ví dụ ánh xạ access denied:

```java
@GraphQlExceptionHandler
GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.FORBIDDEN)
        .message("You are not allowed to access this resource")
        .extensions(Map.of("code", "ACCESS_DENIED"))
        .build();
}
```

Authentication và authorization cần được kiểm tra ở đúng lớp. Không nên dựa vào `extensions.code` để thay thế việc xác minh credentials hoặc thực thi quyền truy cập thực tế.

## 11. GraphQL errors không đồng nghĩa HTTP status

GraphQL thường dùng một endpoint cho nhiều operation. Vì vậy, HTTP status không phải cách duy nhất để client biết field nào thành công hoặc thất bại.

Ví dụ:

- Request bị chặn bởi Spring Security trước GraphQL có thể trả HTTP `401` hoặc `403`.
- Một GraphQL operation đã được thực thi nhưng một resolver ném exception có thể vẫn trả HTTP response chứa `data` và `errors`.
- Business error trong payload có thể trả trong `data` mà không có top-level `errors`.
- Request error trước execution có status phụ thuộc transport, media type và quy tắc triển khai GraphQL over HTTP; không nên giả định mọi lỗi đều dùng cùng một status.

Với HTTP GraphQL, hãy đọc response body theo hợp đồng GraphQL và kiểm tra `data`/`errors`. Với WebSocket, GraphQL operation errors được gửi trong payload của protocol; lỗi protocol hoặc lỗi kết nối là một lớp khác.

Không nên dùng HTTP `200` để kết luận mọi field thành công, cũng không nên giả định HTTP `4xx` luôn chứa GraphQL `errors`. Client cần xử lý cả lớp transport lẫn lớp GraphQL.

## 12. Thiết kế mã lỗi ổn định

`message` dành cho con người, có thể thay đổi hoặc được dịch. Client nên dựa vào mã lỗi ổn định trong `extensions.code` hoặc trong payload `userErrors.code`.

Một bộ mã có thể được thiết kế như sau:

| Code | Nhóm | Hành động client |
|---|---|---|
| `BOOK_NOT_FOUND` | Resource | Hiển thị thông báo không tìm thấy hoặc điều hướng lại. |
| `DUPLICATE_EMAIL` | Business validation | Đánh dấu field email và yêu cầu nhập địa chỉ khác. |
| `ACCESS_DENIED` | Authorization | Hiển thị thông báo không đủ quyền. |
| `INVALID_STATE` | Business rule | Yêu cầu người dùng thực hiện bước hợp lệ tiếp theo. |
| `INTERNAL_ERROR` | Unexpected failure | Hiển thị thông báo chung và mã hỗ trợ nếu có. |

Nên tài liệu hóa:

1. Mã lỗi và ý nghĩa của nó.
2. Lỗi nằm trong top-level `errors` hay payload.
3. Có `path`, `locations` hoặc field path hay không.
4. Client có thể retry hay cần người dùng sửa dữ liệu.
5. Thông tin nào được phép xuất hiện trong `message` và `extensions`.

Không dùng message để làm mã lỗi, không đổi code tùy tiện giữa các phiên bản và không đưa stack trace, SQL, token, email nội bộ hoặc thông tin nhạy cảm vào response.

## 13. Kiểm thử từng nhóm lỗi bằng `GraphQlTester`

`GraphQlTester` cho phép kiểm tra cả GraphQL data và danh sách errors. Với execution error, có thể kiểm tra mã lỗi và field path:

```java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            bookById(id: "missing-book") {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getPath())
        .containsExactly("bookById");
    assertThat(errors.get(0).getExtensions())
        .containsEntry("code", "BOOK_NOT_FOUND");
});

response.path("bookById").valueIsNull();
```

Ví dụ minh họa; `graphQlTester`, controller, exception advice và SDL cần được cấu hình trong test context. Nếu field có alias hoặc nested path, hãy assert đúng response path.

Với request error, gửi document sai schema hoặc variables không hợp lệ và xác nhận resolver không được gọi. Tùy test setup, có thể kiểm tra `errors()` mà không truy cập field data.

Với business error, kiểm tra payload:

```java
graphQlTester.document("""
        mutation {
            registerUser(input: {
                email: "existing@example.com"
                name: "An"
            }) {
                user { id }
                userErrors {
                    code
                    field
                }
            }
        }
        """)
    .execute()
    .path("registerUser.userErrors[0].code")
    .entity(String.class)
    .isEqualTo("DUPLICATE_EMAIL");
```

Ma trận kiểm thử nên bao gồm:

- Parse error: document sai cú pháp.
- Validation error: field hoặc argument không tồn tại.
- Variable coercion error: thiếu biến Non-null hoặc sai kiểu.
- Execution error: resolver ném exception và được ánh xạ đúng.
- Partial data: field nullable lỗi nhưng field sibling vẫn trả dữ liệu.
- Non-null propagation: xác minh lỗi lan tới nullable boundary dự kiến.
- Business error: payload chứa code và field path, không có top-level error nếu hợp đồng quy định như vậy.
- Security error: kiểm tra đúng tầng từ chối và không rò rỉ dữ liệu.

## 14. Lỗi thường gặp khi phân loại

**Gọi mọi lỗi là `INTERNAL_ERROR`.** Client không thể phân biệt lỗi đầu vào, thiếu quyền, tài nguyên không tồn tại và lỗi hệ thống. Hãy phân loại theo nguyên nhân.

**Dùng exception cho mọi business validation.** Những trạng thái dự kiến mà người dùng có thể sửa thường phù hợp với payload `userErrors`.

**Cho rằng request error đi qua resolver.** Parse, validation và variable coercion xảy ra trước data fetching. Sửa document hoặc variables ở client.

**Cho rằng có `errors` nghĩa là `data` luôn null.** Execution error có thể chỉ làm một field thành `null`; các field khác vẫn có dữ liệu.

**Không hiểu null propagation.** Field Non-null nhận `null` có thể làm parent thành `null` và lan lên root. Hãy kiểm tra SDL cùng test response.

**Để client phân tích message.** Message có thể thay đổi hoặc được dịch. Dùng mã lỗi ổn định trong `extensions` hoặc payload.

**Đồng nhất GraphQL error với HTTP status.** Một response GraphQL có thể chứa partial data và errors. Cần xử lý cả transport status và GraphQL body.

**Đưa chi tiết nội bộ vào error response.** Không trả stack trace, SQL, token hoặc thông tin hạ tầng cho client. Ghi chi tiết ở server và trả mã lỗi an toàn.

## Kết luận

Error classification trong GraphQL bắt đầu bằng việc xác định lỗi xuất hiện trước execution, trong quá trình field execution hay là một kết quả nghiệp vụ dự kiến. Request errors yêu cầu client sửa document hoặc variables; execution errors được biểu diễn qua top-level `errors` và có thể đi kèm partial data; business errors thường được mô hình hóa bằng payload có mã lỗi và field path. Trong Spring for GraphQL, dùng `ErrorType`, `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` cho exception từ resolver, đồng thời giữ nullability và error contract nhất quán. Kiểm thử cả `data`, `errors`, `path`, `extensions` và transport status để client có thể xử lý lỗi chính xác.

## Tài liệu tham khảo

- [GraphQL Specification — Response](https://spec.graphql.org/October2021/#sec-Response)
- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html)
