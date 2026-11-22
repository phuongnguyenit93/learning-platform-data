# Phân biệt argument omitted và null trong GraphQL

Trong GraphQL, một argument hoặc input field có thể bị bỏ qua, được gửi với giá trị `null`, hoặc được gửi với một giá trị cụ thể. Ba trạng thái này có ý nghĩa khác nhau. Đặc biệt với mutation cập nhật từng phần, server thường cần biết client không đề cập đến một field hay chủ động yêu cầu xóa giá trị của field đó.

Spring for GraphQL cung cấp `ArgumentValue<T>` để giữ lại sự khác biệt giữa một argument bị bỏ qua và một argument được gửi rõ ràng với giá trị null. Wrapper này có thể dùng cho argument ở cấp resolver và field bên trong input object. Khi hiểu đúng semantics của GraphQL và giữ trạng thái này qua service boundary, ứng dụng có thể triển khai partial update mà không vô tình xóa dữ liệu.

Sau bài này, bạn có thể:

- Phân biệt argument/input field bị omitted, explicit null và có giá trị.
- Hiểu cách GraphQL áp dụng default value cho argument, variable và input field.
- Nhận biết khi nào schema non-null từ chối omitted hoặc null trước resolver.
- Dùng `ArgumentValue<T>` ở top-level argument và nested input object.
- Giữ semantics khi chuyển GraphQL input thành application command.
- Thiết kế mutation cập nhật từng phần với quy tắc rõ ràng.
- Kiểm thử ba trạng thái bằng `GraphQlTester`.

## 1. Ba trạng thái của một input field

Xét input type:

```graphql
input UpdateBookInput {
    title: String
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Với field `subtitle`, client có thể gửi ba dạng:

```graphql
# 1. Bỏ qua subtitle
mutation {
    updateBook(id: "book-42", input: { title: "New title" }) {
        id
    }
}

# 2. Gửi subtitle với giá trị null
mutation {
    updateBook(id: "book-42", input: {
        title: "New title"
        subtitle: null
    }) {
        id
    }
}

# 3. Gửi subtitle với một giá trị
mutation {
    updateBook(id: "book-42", input: {
        title: "New title"
        subtitle: "A practical guide"
    }) {
        id
    }
}
```

Ba trường hợp này có thể được diễn giải như sau:

| Trạng thái | Ý nghĩa từ phía client | Cách xử lý thường gặp trong partial update |
| --- | --- | --- |
| Omitted | Client không đề cập field | Giữ nguyên giá trị hiện tại |
| Explicit `null` | Client chủ động gửi null | Xóa giá trị hoặc xử lý theo quy tắc nghiệp vụ |
| Có giá trị | Client gửi giá trị mới | Thay thế giá trị hiện tại |

GraphQL giữ được sự khác biệt giữa field không xuất hiện và field có giá trị null trong input đã được coercion. Vấn đề thường xuất hiện ở bước bind vào Java object: nếu cả hai trạng thái đều được gán thành `null`, ứng dụng sẽ mất thông tin mà client đã gửi.

## 2. Omitted không đồng nghĩa với null

Omitted có nghĩa key không xuất hiện trong input object hoặc argument không được cung cấp. Explicit null có nghĩa key có xuất hiện và giá trị của nó là `null`.

Ví dụ hai JSON variables sau không giống nhau:

```json
{
  "input": {
    "title": "New title"
  }
}
```

```json
{
  "input": {
    "title": "New title",
    "subtitle": null
  }
}
```

Trong object đầu tiên, `subtitle` bị bỏ qua. Trong object thứ hai, client gửi `subtitle` với giá trị null. Nếu API dùng `null` để xóa subtitle, hai request phải tạo ra hai kết quả khác nhau.

Điều này cũng áp dụng cho argument ở cấp field:

```graphql
type Query {
    books(status: BookStatus): [Book!]!
}
```

`books` có thể được gọi mà không truyền `status`, hoặc truyền `status: null`. Nếu ứng dụng phân biệt hai trường hợp, resolver phải giữ được thông tin về sự hiện diện của argument.

## 3. Default value thay đổi semantics của omitted

GraphQL cho phép khai báo default value ở argument, variable và input field. Default được dùng khi giá trị tương ứng bị bỏ qua; explicit null vẫn là null nếu kiểu cho phép null.

Default ở argument:

```graphql
type Query {
    books(limit: Int = 20): [Book!]!
}
```

Khi client bỏ qua `limit`, resolver nhận giá trị mặc định `20`. Nếu client gửi `limit: null`, default không được dùng và resolver nhận null, vì argument nullable.

Default ở variable:

```graphql
query Books($limit: Int = 20) {
    books(limit: $limit) {
        id
        title
    }
}
```

Nếu client không gửi variable `limit`, default `20` của variable được áp dụng. Nếu client gửi `"limit": null`, giá trị null được sử dụng và default không thay thế nó.

Default ở input field:

```graphql
input BookFilter {
    status: BookStatus = PUBLISHED
}
```

Khi `status` bị bỏ qua, quá trình input coercion áp dụng `PUBLISHED`. Vì vậy, nếu mục tiêu là phân biệt field không được cung cấp để giữ nguyên dữ liệu, không nên khai báo default trên field patch đó. Default có thể làm mất ý nghĩa “không thay đổi” trước khi resolver xử lý input.

## 4. Non-null từ chối cả omitted lẫn null

Với kiểu non-null, client phải cung cấp một giá trị khác null:

```graphql
input CreateBookInput {
    title: String!
}
```

Các request sau không hợp lệ:

```graphql
# Thiếu title
mutation {
    createBook(input: {}) {
        id
    }
}

# title là null
mutation {
    createBook(input: { title: null }) {
        id
    }
}
```

GraphQL từ chối input ở bước validation/coercion trước khi gọi resolver. Đây là lựa chọn phù hợp cho thao tác tạo mới khi title bắt buộc phải có.

Với partial update, một field có thể được phép omitted nhưng không được phép null. Nếu khai báo `String!`, GraphQL sẽ từ chối cả hai trường hợp. Nếu cần cho phép omitted và muốn tự xử lý explicit null, khai báo field nullable rồi kiểm tra null trong service. Ví dụ, `title` có thể được bỏ qua để giữ nguyên, nhưng nếu client gửi null thì service trả lỗi nghiệp vụ vì sách bắt buộc có tiêu đề.

## 5. ArgumentValue<T> trong Spring for GraphQL

Nếu method resolver nhận trực tiếp một kiểu nullable như `String`, cả omitted và explicit null có thể cùng được bind thành `null`. `ArgumentValue<T>` giữ thêm trạng thái cho biết argument có bị bỏ qua hay không.

Ví dụ với argument cấp cao nhất:

```graphql
type Query {
    books(status: BookStatus): [Book!]!
}
```

```java
@QueryMapping
public List<BookView> books(
        @Argument("status") ArgumentValue<BookStatus> status) {

    if (status.isOmitted()) {
        return bookService.findAll();
    }

    if (status.value() == null) {
        return bookService.findWithoutStatus();
    }

    return bookService.findByStatus(status.value());
}
```

Trong ví dụ này:

- `isOmitted()` là `true` khi client không cung cấp argument `status`.
- `isOmitted()` là `false` khi client có cung cấp argument, kể cả khi giá trị được gửi là null.
- `value()` trả giá trị đã bind; với explicit null, giá trị này là null.

Nếu argument có default value trong SDL, GraphQL áp dụng default khi client bỏ qua argument. Khi đó resolver nhận giá trị mặc định thay vì trạng thái omitted. Vì vậy, chỉ khai báo default khi đó thực sự là semantics mong muốn.

## 6. Dùng ArgumentValue bên trong input object

`ArgumentValue<T>` cũng có thể được dùng trong các field của record hoặc DTO nhận input object. Đây là trường hợp quan trọng với mutation cập nhật từng phần:

```graphql
input UpdateBookInput {
    title: String
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Java record:

```java
public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> subtitle) {
}
```

Controller:

```java
@MutationMapping
public BookView updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {

    return bookService.update(new UpdateBookCommand(
            id,
            toPatch(input.title()),
            toPatch(input.subtitle())));
}

private FieldPatch<String> toPatch(ArgumentValue<String> value) {
    if (value.isOmitted()) {
        return FieldPatch.omitted();
    }
    return FieldPatch.supplied(value.value());
}
```

`ArgumentValue` giữ trạng thái ở bước binding của Spring for GraphQL. Khi chuyển dữ liệu sang application service, nên chuyển nó thành một kiểu command của ứng dụng để service không phụ thuộc vào lớp GraphQL.

## 7. Giữ trạng thái omitted trong application command

Một command đơn giản có thể biểu diễn field patch bằng hai thông tin: field có được cung cấp hay không và giá trị được cung cấp là gì.

```java
public record FieldPatch<T>(boolean supplied, T value) {

    public static <T> FieldPatch<T> omitted() {
        return new FieldPatch<>(false, null);
    }

    public static <T> FieldPatch<T> supplied(T value) {
        return new FieldPatch<>(true, value);
    }
}

public record UpdateBookCommand(
        String bookId,
        FieldPatch<String> title,
        FieldPatch<String> subtitle) {
}
```

Giờ service có thể phân biệt rõ ba trạng thái:

```java
@Transactional
public BookView update(UpdateBookCommand command) {
    BookEntity book = bookRepository.findById(command.bookId())
            .orElseThrow(() -> new BookNotFoundException(command.bookId()));

    if (command.title().supplied()) {
        String title = command.title().value();
        if (title == null || title.isBlank()) {
            throw new InvalidBookTitleException();
        }
        book.rename(title);
    }

    if (command.subtitle().supplied()) {
        book.changeSubtitle(command.subtitle().value());
    }

    return bookMapper.toView(book);
}
```

Kết quả:

- `title` omitted: giữ tiêu đề hiện tại.
- `title` explicit null: từ chối vì tiêu đề không được null.
- `title` có chuỗi hợp lệ: đổi tiêu đề.
- `subtitle` omitted: giữ subtitle hiện tại.
- `subtitle` explicit null: xóa subtitle.
- `subtitle` có chuỗi: thay subtitle.

Kiểu `FieldPatch` chỉ là một lựa chọn biểu diễn command. Dự án có thể dùng sealed interface hoặc kiểu `PatchField<T>` riêng để làm rõ hơn các trạng thái. Điều quan trọng là không làm mất thông tin presence khi chuyển qua service boundary.

## 8. Vì sao Optional<T> thường không đủ?

`Optional<T>` biểu diễn có hoặc không có một giá trị. Nhưng với partial update, ứng dụng cần ít nhất ba trạng thái: omitted, explicit null và giá trị cụ thể.

Nếu cả omitted và explicit null đều được chuyển thành `Optional.empty()`, service không thể biết client muốn giữ nguyên field hay xóa nó. `Optional` vẫn hữu ích khi chỉ cần biểu diễn có/không có giá trị, nhưng không thay thế `ArgumentValue<T>` khi cần giữ presence semantics của GraphQL input.

Tương tự, một DTO thông thường:

```java
public record UpdateBookInput(String title, String subtitle) {
}
```

có thể nhận `null` cho cả field bị bỏ qua và field explicit null. DTO này đủ dùng nếu ứng dụng cố ý coi hai trường hợp giống nhau. Nếu nghiệp vụ cần phân biệt, hãy dùng `ArgumentValue<T>` ở các field cần presence tracking hoặc bind vào một cấu trúc giữ được key presence.

## 9. Đọc presence ở mức DataFetchingEnvironment

Trong một resolver cần truy cập API GraphQL Java ở mức thấp hơn, có thể xem map argument và kiểm tra key có tồn tại hay không:

```java
@QueryMapping
public List<BookView> books(DataFetchingEnvironment environment) {
    Map<String, Object> arguments = environment.getArguments();

    if (!arguments.containsKey("status")) {
        return bookService.findAll();
    }

    BookStatus status = (BookStatus) arguments.get("status");
    if (status == null) {
        return bookService.findWithoutStatus();
    }

    return bookService.findByStatus(status);
}
```

`containsKey` phân biệt key không tồn tại với key có giá trị null. Cách này hữu ích khi cần đọc nhiều argument động hoặc xử lý cấu trúc map. Với annotated controller và tham số có kiểu rõ ràng, `ArgumentValue<T>` thường ngắn gọn và dễ kiểm thử hơn.

Với input object lồng nhau, phải kiểm tra key ở đúng map tương ứng. Không nên tự chuyển toàn bộ resolver sang xử lý map nếu một DTO có kiểu rõ ràng đáp ứng được yêu cầu.

## 10. Variables và omitted/null

GraphQL variables được gửi bằng JSON. Với operation:

```graphql
mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
    updateBook(id: $id, input: $input) {
        id
        title
        subtitle
    }
}
```

Variables không có key `subtitle`:

```json
{
  "id": "book-42",
  "input": {
    "title": "New title"
  }
}
```

Variables có key `subtitle` với null:

```json
{
  "id": "book-42",
  "input": {
    "title": "New title",
    "subtitle": null
  }
}
```

Nếu operation tham chiếu một variable nullable mà client không gửi và variable không có default, biến không được xác định. Khi biến đó được dùng làm giá trị của input object field, field tương ứng có thể bị loại khỏi input sau coercion; explicit JSON null vẫn là một giá trị được cung cấp. Vì vậy, cần kiểm tra cả cách operation khai báo variables và object JSON mà client gửi.

Đừng nhầm một JSON object có key với giá trị null với một JSON object không có key. Client code đôi khi tự động serialize thuộc tính không xác định thành null; điều này có thể làm server hiểu rằng client yêu cầu xóa field. Hãy kiểm tra payload thực tế được gửi qua HTTP.

## 11. Không đặt default trên field patch nếu omission nghĩa là giữ nguyên

Xét schema:

```graphql
input UpdateBookInput {
    subtitle: String = "Untitled"
}
```

Nếu client bỏ qua `subtitle`, GraphQL áp dụng default `"Untitled"`. Service sẽ nhận một giá trị được cung cấp thay vì trạng thái omitted và có thể ghi đè subtitle hiện tại.

Với input dành cho partial update, thường nên khai báo field nullable và không có default:

```graphql
input UpdateBookInput {
    subtitle: String
}
```

Sau đó dùng `ArgumentValue<String>` để quyết định omitted là giữ nguyên và null là xóa. Nếu muốn default cho thao tác tạo mới, có thể khai báo default ở input type riêng dành cho create hoặc áp dụng default trong service khi field thực sự bị omitted.

Tách `CreateBookInput` và `UpdateBookInput` thường giúp semantics rõ ràng hơn vì tạo mới và cập nhật từng phần có quy tắc bắt buộc/optional khác nhau.

## 12. Validation khi field có thể omitted hoặc null

Bean Validation cần phù hợp với semantics đã chọn. Nếu một field nullable được dùng để yêu cầu xóa giá trị, đặt `@NotNull` trực tiếp lên field đó sẽ khiến thao tác xóa không thể thực hiện. Nếu field bị omitted được phép giữ nguyên nhưng explicit null không hợp lệ, validation cần chạy có điều kiện dựa trên presence.

Ví dụ:

```java
if (!input.title().isOmitted()) {
    String title = input.title().value();
    if (title == null || title.isBlank()) {
        throw new InvalidBookTitleException();
    }
}
```

Các quy tắc liên quan nhiều field hoặc trạng thái hiện tại của resource nên được kiểm tra trong service/domain. Ví dụ, client có thể bỏ qua `status`, nhưng nếu gửi `status: null` thì domain không cho phép xóa trạng thái. Service phải kiểm tra và trả lỗi nghiệp vụ.

Với field non-null trong SDL, GraphQL đã từ chối omitted và null trước resolver. Với field nullable, validation ở ứng dụng quyết định null có được chấp nhận theo nghiệp vụ hay không.

## 13. Kiểm thử ba trạng thái bằng GraphQlTester

`GraphQlTester` cho phép truyền variables dưới dạng map để kiểm tra chính xác key có xuất hiện hay không.

Trường hợp omitted:

```java
Map<String, Object> input = new HashMap<>();
input.put("title", "New title");

graphQlTester.document("""
        mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
            updateBook(id: $id, input: $input) {
                id
                title
                subtitle
            }
        }
        """)
    .variable("id", "book-42")
    .variable("input", input)
    .execute();
```

Trường hợp explicit null:

```java
Map<String, Object> input = new HashMap<>();
input.put("title", "New title");
input.put("subtitle", null);

graphQlTester.document("""
        mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
            updateBook(id: $id, input: $input) {
                id
                title
                subtitle
            }
        }
        """)
    .variable("id", "book-42")
    .variable("input", input)
    .execute();
```

Dùng `HashMap` ở test explicit null vì `Map.of(...)` không cho phép value null. Với cả ba trường hợp, nên xác nhận service nhận đúng command và dữ liệu lưu cuối cùng có đúng semantics.

Các test cần có:

1. Field omitted được đánh dấu omitted và không làm thay đổi dữ liệu hiện tại.
2. Explicit null được giữ lại và xử lý theo quy tắc xóa hoặc validation.
3. Giá trị cụ thể được bind và cập nhật đúng.
4. Default value được áp dụng khi omitted nếu schema có khai báo default.
5. Non-null argument/input field bị từ chối trước khi resolver chạy khi omitted hoặc null.
6. Variable không được gửi khác với variable được gửi explicit null.
7. Nested input object giữ được presence của field cần patch.
8. Lỗi validation hoặc lỗi nghiệp vụ được trả về theo GraphQL contract.

## 14. Những lỗi thường gặp

- **Coi omitted giống null:** có thể xóa dữ liệu khi client chỉ muốn cập nhật field khác.
- **Bind vào DTO nullable thông thường rồi cố khôi phục presence:** thông tin key đã bị mất; dùng `ArgumentValue<T>` từ bước binding.
- **Dùng `Optional<T>` cho partial update:** có thể gộp explicit null và omitted thành cùng một trạng thái.
- **Khai báo default trên field patch:** omission bị thay bằng default và có thể ghi đè dữ liệu hiện tại.
- **Đánh dấu field `!` nhưng mong omitted được phép:** non-null buộc client phải gửi giá trị khác null.
- **Dùng primitive Java cho input nullable:** primitive như `int` không biểu diễn được null; dùng wrapper như `Integer` khi cần.
- **Đặt `@NotNull` trên field cho phép xóa:** validation sẽ từ chối explicit null dù đó là thao tác hợp lệ.
- **Serialize thuộc tính không xác định thành null ở client:** server hiểu nhầm thành yêu cầu xóa.
- **Chuyển `ArgumentValue` sâu vào domain/service:** application layer bị phụ thuộc Spring for GraphQL; chuyển sang command type riêng.
- **Chỉ test giá trị cuối cùng:** cần xác nhận cả ba trạng thái và việc service được gọi với command phù hợp.

## 15. Quy trình thiết kế argument omitted và null

Khi thiết kế query hoặc mutation có input tùy chọn, hãy thực hiện:

1. Xác định field nào được phép bỏ qua, field nào cho phép explicit null và field nào bắt buộc.
2. Chọn nullability trong SDL theo hợp đồng; dùng non-null khi cả omitted và null đều phải bị từ chối.
3. Chỉ khai báo default nếu omission thực sự phải được thay bằng một giá trị mặc định.
4. Với partial update, tránh default trên field mà omitted có nghĩa giữ nguyên.
5. Dùng `ArgumentValue<T>` cho top-level argument hoặc nested input field cần phân biệt presence.
6. Chuyển trạng thái sang application command có kiểu riêng trước khi gọi service.
7. Thực hiện validation có điều kiện và quy tắc cập nhật trong service/domain.
8. Kiểm tra client JSON serialization để không biến omitted thành null ngoài ý muốn.
9. Kiểm thử omitted, explicit null, giá trị cụ thể, default và non-null validation bằng GraphQlTester.

Omitted và explicit null là hai tín hiệu khác nhau trong hợp đồng GraphQL. Với thao tác tạo mới, non-null và default value giúp kiểm soát dữ liệu bắt buộc; với partial update, `ArgumentValue<T>` giúp Spring for GraphQL giữ lại việc client có cung cấp field hay không. Khi truyền presence semantics qua application command và kiểm thử cả ba trạng thái, service có thể giữ nguyên, xóa hoặc thay đổi dữ liệu đúng theo ý định của client.

## Tài liệu tham khảo

- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
- [GraphQL Specification — Input Coercion](https://spec.graphql.org/October2021/#sec-Input-Coercion)
- [Spring for GraphQL — Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.arguments)
- [Spring for GraphQL — ArgumentValue API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/ArgumentValue.html)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
