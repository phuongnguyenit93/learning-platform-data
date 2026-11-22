# type Mutation

Trong GraphQL, `type Mutation` khai báo các thao tác có thể làm thay đổi trạng thái của hệ thống, chẳng hạn tạo đơn hàng, cập nhật hồ sơ, xác nhận thanh toán hoặc xóa một tài nguyên. Đây là một phần của schema SDL, mô tả những command mà client được phép yêu cầu và kiểu dữ liệu server trả về.

Với Spring for GraphQL, các field khai báo trong root mutation type thường được ánh xạ tới method Java bằng `@MutationMapping`. Starter cung cấp nền tảng thực thi, còn schema và resolver vẫn cần được ứng dụng thiết kế theo nghiệp vụ.

## 1. Mutation là gì?

GraphQL định nghĩa ba loại operation thường gặp:

- `query` đọc dữ liệu.
- `mutation` yêu cầu thực hiện thay đổi có tác dụng phụ.
- `subscription` nhận các sự kiện hoặc cập nhật theo thời gian.

Root type của mutation là một object type trong schema. Theo quy ước phổ biến, object type này có tên `Mutation`:

```graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    createBook(title: String!): Book!
    deleteBook(id: ID!): Boolean!
}

type Book {
    id: ID!
    title: String!
}
```

Schema trên công bố hai thao tác: tạo sách và xóa sách. Client không gọi một URL riêng cho từng mutation; client gửi một GraphQL operation tới endpoint và chọn field muốn thực thi.

Schema GraphQL bắt buộc có query root type, nhưng mutation root type là tùy chọn. Một API chỉ đọc dữ liệu có thể không khai báo `type Mutation`. Khi schema có mutation, root type phải là object type có ít nhất một field.

Tên `Mutation` là quy ước mặc định. Nếu muốn dùng tên khác, cần ánh xạ root operation type tường minh trong schema:

```graphql
schema {
    query: RootQuery
    mutation: Commands
}

type RootQuery {
    book(id: ID!): Book
}

type Commands {
    createBook(title: String!): Book!
}
```

Khi đó `Commands` là mutation root type của schema, dù tên type không phải `Mutation`.

## 2. Khai báo field trong type Mutation

Mỗi field trong `type Mutation` đại diện cho một thao tác mà client có thể yêu cầu. Một field có thể nhận argument và trả về scalar, enum hoặc object type.

Ví dụ:

```graphql
type Mutation {
    createBook(title: String!, author: String!): Book!
    renameBook(id: ID!, newTitle: String!): Book!
    publishBook(id: ID!): Book!
    deleteBook(id: ID!): Boolean!
}
```

Khi thiết kế field, hãy thể hiện ý định nghiệp vụ bằng tên rõ nghĩa như `createBook`, `publishBook` hoặc `cancelOrder`. Tên như `update`, `execute` hoặc `process` không cho biết client đang yêu cầu thay đổi gì.

Argument nên mô tả dữ liệu tối thiểu cần thiết cho command. Dùng `ID!` cho định danh, scalar phù hợp cho giá trị đơn giản và input object khi thao tác nhận nhiều trường.

Kiểu trả về cần phản ánh kết quả mà client cần để cập nhật giao diện hoặc tiếp tục luồng nghiệp vụ. Trả về `Boolean!` có thể đủ cho một thao tác đơn giản, nhưng thường một object payload hữu ích hơn vì client có thể nhận entity vừa tạo, trạng thái mới hoặc thông tin lỗi kiểm tra dữ liệu.

## 3. Dùng input object cho dữ liệu đầu vào

Khi mutation có nhiều argument, gom chúng vào một `input` type giúp schema gọn và dễ mở rộng. GraphQL phân biệt rõ object type dùng cho dữ liệu đầu ra và input object type dùng cho dữ liệu đầu vào.

Ví dụ:

```graphql
input CreateBookInput {
    title: String!
    authorName: String!
    isbn: String
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

Client gửi operation và variables:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        authorName
    }
}
```

Variables được truyền riêng với document:

```json
{
  "input": {
    "title": "GraphQL thực hành",
    "authorName": "Nguyen An",
    "isbn": "9780000000001"
  }
}
```

Input object có các giới hạn quan trọng:

- Field của input object phải dùng kiểu đầu vào hợp lệ như scalar, enum, input object hoặc list của các kiểu đầu vào.
- Không thể dùng một output object type như `Book` làm kiểu của field trong `input`.
- Input object không có field resolver hoặc argument như output object field.
- Có thể dùng `!` để yêu cầu client cung cấp giá trị và dùng giá trị mặc định khi phù hợp.

Ví dụ dưới đây không hợp lệ vì `Book` là output object type:

```graphql
input InvalidBookInput {
    book: Book
}
```

Nếu cần truyền một cấu trúc lồng nhau, hãy định nghĩa một input type riêng:

```graphql
input AuthorInput {
    name: String!
    email: String
}

input CreateBookInput {
    title: String!
    author: AuthorInput!
}
```

Không nên tái sử dụng output type làm input chỉ để tránh khai báo thêm type. Dữ liệu client được phép gửi và dữ liệu server được phép trả về thường có mục đích, quyền truy cập và vòng đời khác nhau.

## 4. Nullability và ý nghĩa của dữ liệu đầu vào

Ký hiệu `!` cho biết giá trị không được null. Với input argument hoặc input field, điều này có nghĩa client phải cung cấp giá trị hợp lệ theo kiểu đã khai báo, trừ khi có giá trị mặc định phù hợp.

```graphql
input UpdateBookInput {
    title: String!
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Trong ví dụ này, `title` bắt buộc phải có và không null. `subtitle` là tùy chọn và có thể nhận null. Với một thao tác cập nhật từng phần, cần thống nhất ý nghĩa của ba trạng thái:

1. Field không xuất hiện trong input: client không yêu cầu thay đổi field đó.
2. Field xuất hiện với giá trị: cập nhật sang giá trị mới.
3. Field xuất hiện với `null`: tùy hợp đồng, có thể yêu cầu xóa giá trị hiện tại.

Không phải mọi kiểu Java đều giữ được sự khác biệt giữa field bị bỏ qua và field được gửi tường minh là `null`. Nếu nghiệp vụ cần phân biệt, resolver cần dùng kiểu biểu diễn argument có thông tin về sự hiện diện của field hoặc cơ chế binding phù hợp, thay vì chỉ dựa vào một thuộc tính Java có thể null.

Nullability của output cũng quan trọng. Ví dụ `Book!` cam kết mutation trả về một object Book khác null khi thực thi thành công. Nếu server không thể trả về object do lỗi nghiệp vụ, có thể thiết kế payload với field `book` nullable và một danh sách lỗi có cấu trúc.

## 5. Thiết kế payload trả về

Một mutation thực tế thường cần trả về nhiều hơn một giá trị. Payload có thể chứa entity kết quả và các lỗi nghiệp vụ mà client có thể hiển thị hoặc xử lý.

Ví dụ:

```graphql
input CreateBookInput {
    title: String!
    authorName: String!
}

type UserError {
    field: String
    code: String!
    message: String!
}

type BookPayload {
    book: Book
    userErrors: [UserError!]!
}

type Mutation {
    createBook(input: CreateBookInput!): BookPayload!
}
```

`BookPayload!` bảo đảm server trả về một payload. `book` có thể null nếu thao tác không thành công do lỗi kiểm tra dữ liệu; `userErrors` luôn là một danh sách, kể cả khi danh sách rỗng.

Client có thể chọn đúng thông tin cần dùng:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        book {
            id
            title
        }
        userErrors {
            field
            code
            message
        }
    }
}
```

Một quy ước response có thể là:

- Thành công: `book` có dữ liệu và `userErrors` là danh sách rỗng.
- Dữ liệu không hợp lệ: `book` là null và `userErrors` mô tả trường hoặc quy tắc bị vi phạm.
- Lỗi hệ thống ngoài dự kiến: phát sinh GraphQL error theo chính sách xử lý lỗi của server.

Payload là một lựa chọn thiết kế, không phải yêu cầu bắt buộc của GraphQL. Với thao tác rất đơn giản, trả về entity hoặc scalar trực tiếp có thể đủ. Hãy chọn hợp đồng sao cho client nhận được thông tin cần thiết mà không phải gọi lại chỉ để biết kết quả vừa tạo.

## 6. Gửi mutation operation

Một mutation operation bắt đầu bằng từ khóa `mutation`, có thể có operation name và khai báo variables:

```graphql
mutation RenameBook($id: ID!, $title: String!) {
    renameBook(id: $id, newTitle: $title) {
        id
        title
    }
}
```

Variables:

```json
{
  "id": "book-42",
  "title": "GraphQL nâng cao"
}
```

Nếu không cần variables, có thể viết giá trị trực tiếp trong document, nhưng variables thường dễ tái sử dụng, kiểm thử và truyền dữ liệu an toàn hơn khi client tạo request.

Một mutation operation có thể chứa nhiều field ở cấp cao nhất:

```graphql
mutation {
    first: renameBook(id: "book-1", newTitle: "Tên mới 1") {
        id
    }
    second: renameBook(id: "book-2", newTitle: "Tên mới 2") {
        id
    }
}
```

Alias `first` và `second` giúp phân biệt hai kết quả cùng gọi một field. Các field mutation cấp cao nhất trong cùng một operation được thực thi tuần tự theo thứ tự xuất hiện trong document. Quy tắc này giúp thao tác sau nhìn thấy tác động của thao tác trước trong cùng operation.

Tuy nhiên, thực thi tuần tự không có nghĩa toàn bộ operation tự động nằm trong một transaction database. Nếu field thứ hai thất bại, GraphQL không tự rollback tác động của field thứ nhất. Transaction boundary phải được thiết kế ở service hoặc tầng persistence theo yêu cầu nghiệp vụ.

## 7. Mutation root và thứ tự thực thi

GraphQL xử lý field của query theo cơ chế thực thi thông thường, trong đó các field có thể được xử lý song song nếu runtime cho phép. Riêng các field cấp cao nhất của mutation phải được thực thi tuần tự.

Ví dụ:

```graphql
mutation Checkout {
    reserveInventory(orderId: "order-10") {
        reservationId
    }
    confirmOrder(orderId: "order-10") {
        status
    }
}
```

Field `confirmOrder` chỉ được thực thi sau khi `reserveInventory` hoàn tất trong cùng operation. Dù vậy, thiết kế như trên chỉ hợp lý nếu API chủ đích cho phép client ghép hai command theo thứ tự. Với quy trình quan trọng cần bảo đảm nguyên tử, nên cân nhắc một mutation nghiệp vụ duy nhất như `checkoutOrder` để server điều phối toàn bộ bước trong transaction hoặc workflow phù hợp.

Mutation là command có tác dụng phụ. Vì vậy:

- Không đặt thao tác ghi dữ liệu trong resolver của query.
- Không giả định client chỉ gửi mutation một lần; timeout và retry có thể làm request được gửi lại.
- Với thao tác tạo thanh toán, đặt hàng hoặc chuyển trạng thái có nguy cơ lặp, hãy cân nhắc idempotency key và quy tắc chống thực hiện trùng.
- Dùng transaction, optimistic locking hoặc cơ chế điều phối phù hợp khi nghiệp vụ cần tính nhất quán.

## 8. Ánh xạ type Mutation với Spring for GraphQL

Sau khi khai báo field trong SDL, Spring for GraphQL có thể ánh xạ field của root mutation type tới method Java bằng `@MutationMapping`.

Với schema:

```graphql
input CreateBookInput {
    title: String!
    authorName: String!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Book {
    id: ID!
    title: String!
    authorName: String!
}
```

Controller có thể viết như sau:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }
}
```

`@MutationMapping` ánh xạ method vào field cùng tên trên mutation root type. `@Argument` lấy input object từ argument `input` và chuyển thành kiểu Java tương ứng. Tên field có thể chỉ định rõ nếu tên method khác tên trong SDL:

```java
@MutationMapping(name = "createBook")
public Book add(@Argument CreateBookInput input) {
    return bookService.create(input);
}
```

Input DTO có thể là Java record:

```java
public record CreateBookInput(
    String title,
    String authorName
) {}
```

Controller nên làm nhiệm vụ nhận input và điều phối service. Quy tắc nghiệp vụ, kiểm tra trùng ISBN, xác thực trạng thái và lưu dữ liệu nên nằm trong service hoặc domain layer để có thể tái sử dụng từ các giao diện khác.

Nếu schema trả về payload, method có thể trả về một DTO tương ứng:

```java
public record UserError(String field, String code, String message) {}

public record BookPayload(Book book, List<UserError> userErrors) {}
```

Kiểu Java phải phù hợp với nullability và cấu trúc mà SDL công bố. Một field output được khai báo `!` không được trả về null trong quá trình thực thi thành công.

## 9. Validation, phân quyền và xử lý lỗi

GraphQL kiểm tra cấu trúc operation và kiểu dữ liệu theo schema, nhưng schema không thay thế validation nghiệp vụ. Ví dụ `title: String!` chỉ yêu cầu có chuỗi khác null; nó không bảo đảm tiêu đề không rỗng, không vượt giới hạn độ dài hoặc không trùng với một bản ghi khác.

Server cần kiểm tra ít nhất các lớp điều kiện sau:

1. **Validation cấu trúc**: input có đúng kiểu, field bắt buộc có được cung cấp và enum có giá trị hợp lệ hay không. GraphQL engine thực hiện phần lớn kiểm tra theo schema.
2. **Validation nghiệp vụ**: dữ liệu có thỏa quy tắc của miền nghiệp vụ, trạng thái hiện tại có cho phép thao tác hay không.
3. **Authorization**: người dùng hiện tại có quyền thực hiện command trên tài nguyên cụ thể hay không.
4. **Concurrency**: dữ liệu có bị thay đổi bởi một request khác kể từ khi client đọc hay không.

Không được tin ID do client gửi là bằng chứng về quyền sở hữu. Server phải kiểm tra quyền trên đối tượng được truy cập, đồng thời tránh trả thông tin nhạy cảm trong error message.

Với lỗi có thể dự đoán như thiếu tiêu đề hoặc ISBN không hợp lệ, payload `userErrors` giúp client hiển thị lỗi theo field. Với lỗi xác thực, phân quyền hoặc lỗi hệ thống, server cần áp dụng chính sách exception handling nhất quán. Không trả stack trace, câu SQL hoặc chi tiết hạ tầng cho client.

Nếu dùng Bean Validation, có thể kết hợp annotation trên input DTO và cấu hình validation phù hợp trong ứng dụng. Dù dùng cơ chế nào, service/domain layer vẫn cần bảo vệ invariant vì command có thể được gọi từ nhiều entry point.

## 10. Những lỗi thiết kế thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng output object làm field của input | Schema không hợp lệ | Tạo input object type riêng |
| Đặt tên mutation quá chung chung | Client khó hiểu tác dụng của command | Dùng tên thể hiện hành động nghiệp vụ |
| Trả về `Boolean` cho mọi thao tác | Client phải gọi thêm query để lấy dữ liệu mới | Trả về entity hoặc payload cần thiết |
| Dùng `String!` thay cho input có cấu trúc | Khó kiểm tra kiểu và mở rộng hợp đồng | Khai báo input object và scalar phù hợp |
| Tin rằng mutation tuần tự là transaction | Có thể để lại thay đổi một phần khi lỗi | Đặt transaction boundary trong service |
| Không kiểm tra quyền trên resource | Người dùng có thể sửa dữ liệu của người khác | Authorization tại service/domain hoặc data access |
| Không xử lý retry | Tạo bản ghi hoặc thanh toán trùng | Thiết kế idempotency cho command phù hợp |
| Trả lỗi nội bộ trực tiếp | Rò rỉ thông tin hệ thống | Chuẩn hóa lỗi và chỉ trả thông tin an toàn |

## 11. Checklist thiết kế một mutation

Trước khi công bố một mutation mới, hãy kiểm tra:

- Field có tên mô tả đúng command nghiệp vụ không?
- Argument đã được gom vào input object khi cấu trúc đủ lớn chưa?
- Kiểu input có phân biệt rõ dữ liệu bắt buộc và tùy chọn không?
- Client có nhận được kết quả đủ để cập nhật giao diện không?
- Lỗi validation có cấu trúc và có thể hiển thị được không?
- Quyền truy cập được kiểm tra cho cả thao tác và tài nguyên đích chưa?
- Retry, transaction và cập nhật đồng thời đã được cân nhắc chưa?
- Resolver có ủy quyền nghiệp vụ cho service/domain layer không?

`type Mutation` là hợp đồng cho các command làm thay đổi trạng thái. Thiết kế tốt cần thể hiện rõ ý định nghiệp vụ, định nghĩa input/output có kiểu, kiểm soát quyền và xử lý lỗi có thể dự đoán. Trong Spring for GraphQL, SDL mô tả command còn `@MutationMapping` kết nối command đó với service thực thi. Khi tách rõ hai vai trò này, schema dễ hiểu với client và logic nghiệp vụ vẫn có thể kiểm thử, tái sử dụng độc lập.
