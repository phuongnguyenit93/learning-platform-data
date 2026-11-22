# List input trong GraphQL và Spring for GraphQL

List input cho phép client gửi nhiều giá trị trong cùng một argument hoặc input object. Thay vì gọi mutation nhiều lần để tạo từng bản ghi, client có thể gửi một danh sách phần tử; thay vì lọc theo một mã duy nhất, query có thể nhận danh sách ID, trạng thái hoặc nhãn. GraphQL SDL mô tả kiểu phần tử, việc danh sách có thể null hay không và từng phần tử có thể null hay không.

Trong Spring for GraphQL, list input được bind vào các kiểu collection của Java như `List<T>`. Khi kết hợp với input object, record hoặc DTO, resolver có thể nhận dữ liệu có cấu trúc và chuyển nó đến service để xác thực, xử lý theo lô hoặc lưu trữ. Thiết kế list cần chú ý cả ngữ nghĩa null, thứ tự, phần tử trùng lặp và giới hạn kích thước đầu vào.

Sau bài này, bạn có thể:

- Khai báo list argument và list field trong input object bằng SDL.
- Đọc đúng ý nghĩa của `[T]`, `[T!]`, `[T]!` và `[T!]!`.
- Truyền list trong GraphQL document và JSON variables.
- Hiểu cách GraphQL coercion một giá trị đơn thành list một phần tử.
- Bind list input vào `List<T>` và DTO/record trong Spring for GraphQL.
- Phân biệt field bị bỏ qua, list rỗng và giá trị `null`.
- Xác thực, giới hạn và xử lý list input an toàn trong query và mutation.

## 1. List input là gì?

Trong GraphQL, list type được khai báo bằng cách đặt kiểu phần tử trong cặp dấu ngoặc vuông. Ví dụ `[ID]` là một danh sách các giá trị ID; `[String!]!` là một danh sách không null, trong đó từng chuỗi cũng không null.

Ví dụ API tìm nhiều cuốn sách theo ID:

```graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

Client gửi nhiều ID trong một operation:

```graphql
query {
    booksByIds(ids: ["book-10", "book-20", "book-30"]) {
        id
        title
    }
}
```

Resolver nhận một list ID, service có thể truy vấn nhiều bản ghi trong một lần hoặc dùng batch API của hệ thống lưu trữ. GraphQL chỉ đảm bảo dữ liệu đầu vào đúng kiểu đã khai báo; việc truy vấn theo lô, giữ thứ tự hoặc loại bỏ ID trùng nhau là quyết định của ứng dụng.

List cũng có thể xuất hiện bên trong input object:

```graphql
input BookSearchInput {
    ids: [ID!]
    statuses: [BookStatus!]
    tags: [String!]
}

type Query {
    searchBooks(input: BookSearchInput!): [Book!]!
}
```

Cách này hữu ích khi một thao tác nhận nhiều nhóm điều kiện liên quan. Input object giúp gom các tham số thành một hợp đồng có cấu trúc, dễ mở rộng hơn khi tính năng cần thêm filter.

## 2. Đọc đúng nullability của list

List có thể kết hợp với non-null ở hai vị trí độc lập: chính list và từng phần tử. Bốn dạng cơ bản là:

| Kiểu SDL | List có thể null? | Phần tử có thể null? | Ý nghĩa |
| --- | --- | --- | --- |
| `[String]` | Có | Có | List có thể null; phần tử có thể null |
| `[String!]` | Có | Không | List có thể null; mọi phần tử phải có giá trị |
| `[String]!` | Không | Có | List phải tồn tại; phần tử có thể null |
| `[String!]!` | Không | Không | List và mọi phần tử đều phải có giá trị |

Ví dụ:

```graphql
input ImportBooksInput {
    optionalTitles: [String]
    titles: [String!]!
    externalCodes: [String]!
}
```

- `optionalTitles` có thể không được gửi, gửi `null`, gửi list rỗng hoặc gửi list có phần tử null.
- `titles` bắt buộc phải là list khác null và không được có phần tử null. List rỗng vẫn hợp lệ vì SDL không quy định số phần tử tối thiểu.
- `externalCodes` bắt buộc phải có list, nhưng từng phần tử có thể null.

`!` không có nghĩa list phải chứa ít nhất một phần tử. Nếu nghiệp vụ yêu cầu tối thiểu một ID hoặc tối đa 100 phần tử, hãy kiểm tra thêm bằng validation ở tầng ứng dụng.

### List lồng nhau

GraphQL cho phép list lồng nhiều cấp:

```graphql
input MatrixInput {
    values: [[Int!]!]!
}
```

`[[Int!]!]!` yêu cầu list ngoài khác null, mỗi list con khác null và từng số nguyên khác null. List ngoài hoặc list con vẫn có thể rỗng. Nếu cần giới hạn số hàng, số cột hoặc tổng số phần tử, phải kiểm tra ở ứng dụng.

## 3. Truyền list trong GraphQL document

Trong GraphQL document, list literal được viết bằng dấu ngoặc vuông, các phần tử phân cách bằng dấu phẩy:

```graphql
query SearchBooks {
    booksByIds(ids: ["book-10", "book-20"]) {
        id
        title
    }
}
```

List có thể chứa scalar, enum hoặc input object. Ví dụ mutation nhận danh sách input object:

```graphql
mutation {
    createBooks(inputs: [
        { title: "GraphQL Basics", authorId: "author-1" }
        { title: "Spring APIs", authorId: "author-2" }
    ]) {
        id
        title
    }
}
```

Mỗi phần tử phải tuân theo kiểu `CreateBookInput`. Nếu một phần tử thiếu field non-null hoặc có giá trị sai kiểu, GraphQL từ chối input trước khi resolver thực thi.

List giữ thứ tự phần tử do client gửi. Nếu API trả kết quả theo đúng thứ tự đầu vào, service cần chủ động bảo toàn thứ tự đó; truy vấn SQL với `WHERE id IN (...)` thường không cam kết thứ tự kết quả giống list ID đầu vào.

## 4. Truyền list qua JSON variables

Trong ứng dụng thực tế, client thường dùng variables để tách dữ liệu khỏi GraphQL document:

```graphql
query FindBooks($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
        title
    }
}
```

Variables được gửi dưới dạng JSON array:

```json
{
  "ids": ["book-10", "book-20", "book-30"]
}
```

Với input object có list field, schema có thể khai báo:

```graphql
input ImportedBookInput {
    title: String!
    authorId: ID!
}

input ImportBooksInput {
    books: [ImportedBookInput!]!
    dryRun: Boolean = false
}

type ImportBooksResult {
    acceptedCount: Int!
    books: [Book!]!
}

type Mutation {
    importBooks(input: ImportBooksInput!): ImportBooksResult!
}
```

Operation và variables tương ứng:

```graphql
mutation ImportBooks($input: ImportBooksInput!) {
    importBooks(input: $input) {
        acceptedCount
        books {
            id
            title
        }
    }
}
```

```json
{
  "input": {
    "books": [
      { "title": "GraphQL Basics", "authorId": "author-1" },
      { "title": "Spring APIs", "authorId": "author-2" }
    ],
    "dryRun": false
  }
}
```

JSON không có kiểu list riêng cho GraphQL; nó dùng array. GraphQL kiểm tra kiểu biến dựa trên khai báo trong operation và schema. Nên dùng variables cho danh sách lớn hoặc dữ liệu thay đổi theo từng request để document dễ cache, đọc và kiểm thử.

## 5. Coercion: giá trị đơn có thể được nhận như list một phần tử

Theo quy tắc input coercion của GraphQL, khi một vị trí yêu cầu list nhưng client cung cấp một giá trị đơn không phải list, GraphQL có thể coercion giá trị đó thành list chứa đúng một phần tử, nếu giá trị đơn hợp lệ với kiểu phần tử.

Với schema:

```graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
```

Hai cách truyền sau đều có thể được coercion thành list một phần tử:

```graphql
query {
    booksByIds(ids: "book-10") {
        id
    }
}
```

```graphql
query FindOne($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
    }
}
```

```json
{
  "ids": "book-10"
}
```

Ở phía resolver, giá trị được bind như một list có một phần tử. Tuy vậy, client nên luôn gửi array khi schema khai báo list. Cách viết nhất quán giúp tránh nhầm lẫn giữa input đơn và input nhiều phần tử, đặc biệt khi sau này dữ liệu chuyển từ một ID sang nhiều ID.

Coercion không biến một giá trị sai kiểu thành hợp lệ. Ví dụ, object không thể tự động chuyển thành `ID`, và một phần tử null vẫn bị từ chối nếu kiểu phần tử là `ID!`.

## 6. Phân biệt omitted, null và empty list

Đây là ba trạng thái khác nhau và thường mang ý nghĩa nghiệp vụ khác nhau:

| Input | Ý nghĩa dữ liệu |
| --- | --- |
| Field bị bỏ qua | Client không cung cấp field đó |
| Field có giá trị `null` | Client cung cấp field và chỉ rõ giá trị null, nếu schema cho phép |
| Field có giá trị `[]` | Client cung cấp một list rỗng |
| Field có giá trị `["a", "b"]` | Client cung cấp hai phần tử theo thứ tự |

Ví dụ input cập nhật từng phần:

```graphql
input UpdateBookInput {
    title: String
    tags: [String!]
}
```

Với `tags`, ứng dụng có thể quy định:

- Bỏ qua `tags`: giữ nguyên tags hiện tại.
- Gửi `tags: null`: xóa hoặc đặt tags về trạng thái chưa xác định, nếu nghiệp vụ cho phép.
- Gửi `tags: []`: xóa toàn bộ tags và lưu danh sách rỗng.
- Gửi `tags: ["graphql", "spring"]`: thay tags bằng hai giá trị mới.

GraphQL giữ được sự khác biệt giữa field không xuất hiện và field có giá trị null trong input map. Tuy nhiên, nếu bind ngay vào DTO có field Java nullable thông thường, cả hai tình huống có thể cùng trở thành `null`. Nếu cần phân biệt, dùng `ArgumentValue<T>` ở tham số resolver hoặc input model hỗ trợ giữ trạng thái field đã được cung cấp.

Ví dụ với argument ở resolver:

```java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("tags") ArgumentValue<List<String>> tags) {

    if (!tags.isOmitted()) {
        return bookService.updateTags(id, tags.value());
    }
    return bookService.findById(id);
}
```

Ở ví dụ này, `isOmitted()` kiểm tra client có bỏ qua argument hay không; `value()` trả giá trị được cung cấp, có thể là null nếu schema cho phép. Với input object lồng nhau, hãy thiết kế DTO/binding sao cho trạng thái omitted được giữ lại nếu nghiệp vụ cần phân biệt.

## 7. Bind list input vào Java List

Spring for GraphQL bind argument vào tham số method thông qua `@Argument`. Với list scalar, có thể nhận trực tiếp `List<T>`:

```graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
```

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> booksByIds(@Argument("ids") List<String> ids) {
        return bookService.findAllByIds(ids);
    }
}
```

Spring for GraphQL sử dụng `GraphQlArgumentBinder` để bind dữ liệu GraphQL vào target Java. Các collection như `List`, `Set` và kiểu collection tương thích có thể được bind khi kiểu phần tử có thể chuyển đổi. Với GraphQL `ID`, dùng `String` thường là lựa chọn đơn giản và rõ ràng; nếu muốn nhận `UUID`, hãy bảo đảm conversion service của ứng dụng có converter phù hợp và kiểm thử dữ liệu sai định dạng.

Đừng dùng raw `List` không có generic type nếu resolver cần biết kiểu phần tử. Khai báo `List<String>`, `List<BookStatus>` hoặc `List<CreateBookInput>` giúp code rõ ràng và hỗ trợ conversion/binding chính xác hơn.

## 8. Bind list object vào record hoặc DTO

Khi mỗi phần tử có nhiều field, nên dùng input object thay vì một danh sách các chuỗi ghép thủ công:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    tags: [String!]!
}

type Mutation {
    createBooks(inputs: [CreateBookInput!]!): [Book!]!
}
```

Java record tương ứng:

```java
public record CreateBookInput(
        String title,
        String authorId,
        List<String> tags) {}
```

Resolver nhận list các record:

```java
@MutationMapping
public List<Book> createBooks(
        @Argument("inputs") List<CreateBookInput> inputs) {
    return bookService.createAll(inputs);
}
```

`GraphQlArgumentBinder` có thể bind input object vào constructor của record hoặc constructor/thuộc tính của DTO phù hợp. Tên field trong SDL cần tương ứng với tên thuộc tính hoặc tham số constructor được bind. Nếu DTO có cấu trúc phức tạp, hãy kiểm tra binding bằng test GraphQL thay vì chỉ kiểm tra constructor Java riêng lẻ.

Một input object cũng có thể chứa list các object lồng nhau:

```graphql
input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input CreateOrderInput {
    customerId: ID!
    lines: [OrderLineInput!]!
}
```

```java
public record OrderLineInput(String productId, Integer quantity) {}

public record CreateOrderInput(
        String customerId,
        List<OrderLineInput> lines) {}
```

Kiểu lồng nhau giúp hợp đồng input phản ánh đúng cấu trúc domain và tránh việc resolver phải tự parse các map không rõ kiểu.

## 9. Xác thực list input

SDL kiểm tra kiểu dữ liệu và nullability, nhưng không diễn đạt được mọi quy tắc nghiệp vụ. Ví dụ `[ID!]!` không giới hạn số lượng ID, không ngăn ID trùng lặp và không bảo đảm ID tồn tại.

Với Bean Validation, có thể đặt ràng buộc lên collection và từng phần tử:

```java
public record BulkBookRequest(
        @NotEmpty
        @Size(max = 100)
        List<@NotBlank String> ids) {}
```

Khi dùng validation trong annotated controller, đánh dấu tham số phù hợp bằng `@Valid` hoặc `@Validated` và bảo đảm ứng dụng đã cấu hình Bean Validation:

```java
@QueryMapping
public List<Book> booksByIds(
        @Argument("input") @Valid BulkBookRequest input) {
    return bookService.findAllByIds(input.ids());
}
```

Tùy phiên bản Spring for GraphQL và cấu hình validation, lỗi có thể được xử lý qua cơ chế validation exception của Spring for GraphQL. Hãy kiểm thử cách lỗi được chuyển thành GraphQL response và cung cấp thông điệp phù hợp cho client.

Các kiểm tra thường cần có:

- List không rỗng khi nghiệp vụ yêu cầu ít nhất một phần tử.
- Số phần tử tối đa để kiểm soát tải và kích thước request.
- Không có phần tử null hoặc chuỗi trắng.
- Không có phần tử trùng lặp nếu danh sách đại diện tập ID duy nhất.
- Giá trị phần tử đúng định dạng, chẳng hạn UUID hoặc mã nghiệp vụ.
- Tất cả ID có tồn tại và người gọi có quyền thao tác trên từng bản ghi.

Validation cú pháp và quyền truy cập là hai việc khác nhau. GraphQL có thể xác nhận `ID` là giá trị hợp lệ theo scalar, nhưng server vẫn phải kiểm tra ID đó tồn tại và thuộc phạm vi người dùng được phép truy cập.

## 10. Xử lý list theo lô trong service

List input thường là cơ hội để giảm số lần gọi repository hoặc dịch vụ bên ngoài. Ví dụ, resolver nhận nhiều ID rồi chuyển một lần đến repository:

```java
public List<Book> findAllByIds(List<String> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return bookRepository.findAllById(ids);
}
```

Tuy nhiên, cần xác định rõ semantics của API:

- **Thứ tự:** repository có thể trả kết quả theo thứ tự riêng. Nếu phải giữ thứ tự input, lập map theo ID rồi dựng lại list theo `ids`.
- **ID không tồn tại:** bỏ qua ID không tìm thấy, trả placeholder, hay từ chối toàn bộ request? Hợp đồng cần nói rõ.
- **ID trùng lặp:** trả kết quả một lần hay lặp lại theo từng vị trí input? Nếu cần giữ trùng lặp, không chuyển list sang `Set` một cách vô thức.
- **Tính nguyên tử:** bulk mutation thành công toàn bộ hay cho phép một số phần tử lỗi? Quy tắc transaction phải được xác định.
- **Giới hạn batch:** database có giới hạn số bind parameter; danh sách rất lớn có thể cần chia thành nhiều batch hoặc dùng cơ chế tải dữ liệu khác.

Nếu cần giữ thứ tự và cả ID trùng lặp, có thể dựng lại kết quả từ map:

```java
public List<Book> findInRequestedOrder(List<String> ids) {
    Iterable<Book> foundBooks = bookRepository.findAllById(ids);
    Map<String, Book> byId = StreamSupport.stream(foundBooks.spliterator(), false)
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();
}
```

Đoạn code này bỏ qua ID không tồn tại nhưng vẫn giữ thứ tự và số lần xuất hiện của những ID tồn tại. Nếu API phải báo lỗi khi thiếu bất kỳ ID nào, hãy kiểm tra tập ID tìm thấy trước khi trả kết quả.

## 11. Bulk mutation và xử lý lỗi từng phần tử

Mutation có thể nhận list input để tạo hoặc cập nhật nhiều đối tượng:

```graphql
type Mutation {
    createBooks(inputs: [CreateBookInput!]!): [Book!]!
}
```

Trước khi triển khai, cần quyết định rõ:

1. Nếu một phần tử không hợp lệ, toàn bộ batch có rollback không?
2. Nếu một phần tử thất bại do quy tắc nghiệp vụ, các phần tử còn lại có tiếp tục không?
3. Response có cần trả lỗi theo từng phần tử hay chỉ một lỗi chung?
4. Thứ tự response có tương ứng thứ tự input không?

Nếu cần kết quả từng phần tử, có thể thiết kế output type tường minh:

```graphql
type CreateBookResult {
    index: Int!
    book: Book
    errorCode: String
    message: String
}

type Mutation {
    createBooks(inputs: [CreateBookInput!]!): [CreateBookResult!]!
}
```

Kiểu kết quả này cho phép trả trạng thái xử lý cho từng vị trí mà không biến lỗi của một phần tử thành lỗi không phân biệt cho cả operation. Nếu chọn transaction all-or-nothing, service nên thực hiện trong một transaction và để lỗi làm rollback theo chính sách đã định. Nếu chọn partial success, service cần xử lý từng phần tử có kiểm soát và không giả định một transaction duy nhất sẽ tự thể hiện được kết quả riêng cho từng phần tử.

## 12. Giới hạn kích thước và bảo vệ API

Một list input lớn có thể làm tăng kích thước HTTP request, số bind parameter, bộ nhớ, thời gian xử lý và tải database. Vì vậy, không nên coi việc SDL khai báo list là đủ để kiểm soát tài nguyên.

Nên áp dụng nhiều lớp giới hạn:

- Giới hạn số phần tử bằng Bean Validation hoặc kiểm tra service.
- Giới hạn kích thước request ở web server/gateway.
- Dùng pagination cho truy vấn đọc danh sách lớn thay vì nhận hàng chục nghìn ID trong một argument.
- Chia batch theo giới hạn driver/database khi cần.
- Đặt timeout, giới hạn concurrency và theo dõi query chậm.
- Kiểm tra quyền truy cập trên từng ID trước khi trả dữ liệu hoặc thay đổi trạng thái.

Không dùng list input như một cách lách pagination hoặc query complexity. Một request chứa một list ID rất lớn vẫn có thể gây tải tương đương một truy vấn nặng. Hãy tính cost dựa trên số phần tử, kiểu thao tác và tài nguyên mà service phải tiêu thụ.

## 13. Kiểm thử list input với GraphQlTester

`GraphQlTester` cho phép gửi operation và kiểm tra dữ liệu được bind, xử lý và trả về:

```java
graphQlTester.document("""
        query FindBooks($ids: [ID!]!) {
            booksByIds(ids: $ids) {
                id
                title
            }
        }
        """)
    .variable("ids", List.of("book-10", "book-20"))
    .execute()
    .path("booksByIds")
    .entityList(BookView.class)
    .hasSize(2);
```

Với list input object:

```java
graphQlTester.document("""
        mutation CreateBooks($inputs: [CreateBookInput!]!) {
            createBooks(inputs: $inputs) {
                id
                title
            }
        }
        """)
    .variable("inputs", List.of(
            Map.of("title", "GraphQL Basics", "authorId", "author-1", "tags", List.of("graphql")),
            Map.of("title", "Spring APIs", "authorId", "author-2", "tags", List.of("spring"))))
    .execute()
    .path("createBooks")
    .entityList(BookView.class)
    .hasSize(2);
```

Nên có test cho:

1. List nhiều phần tử được bind đúng thứ tự.
2. List rỗng được xử lý theo hợp đồng.
3. Giá trị list null và phần tử null bị từ chối khi schema yêu cầu non-null.
4. Field bị bỏ qua và field gửi null có hành vi đúng với patch semantics.
5. Singleton coercion được hiểu đúng; client chính thức vẫn gửi array nhất quán.
6. Phần tử sai kiểu hoặc enum value không hợp lệ bị từ chối trước resolver.
7. List vượt giới hạn bị validation từ chối.
8. ID trùng lặp, ID không tồn tại và thứ tự kết quả tuân theo quy tắc đã chọn.
9. Bulk mutation thực hiện transaction hoặc partial success đúng thiết kế.

## 14. Những lỗi thường gặp

- **Nhầm `[T]!` với `[T!]`:** một kiểu bắt buộc list khác null, kiểu còn lại bắt buộc từng phần tử khác null.
- **Cho rằng `!` bắt buộc list có phần tử:** list rỗng vẫn hợp lệ nếu không có validation bổ sung.
- **Gộp omitted, null và `[]`:** có thể khiến mutation cập nhật từng phần thay đổi dữ liệu ngoài ý muốn.
- **Dùng raw `List`:** mất thông tin kiểu phần tử và làm binding khó kiểm soát.
- **Giả định repository giữ thứ tự input:** nhiều truy vấn `IN` không đảm bảo thứ tự.
- **Chuyển list sang `Set` quá sớm:** làm mất thứ tự và phần tử trùng lặp.
- **Không giới hạn số phần tử:** request lớn có thể làm cạn bộ nhớ hoặc vượt giới hạn database.
- **Cho rằng GraphQL tự kiểm tra ID tồn tại và quyền truy cập:** scalar `ID` chỉ kiểm tra kiểu, không xác thực bản ghi hay quyền.
- **Giả định bulk mutation luôn nguyên tử:** transaction và chính sách partial success phải do ứng dụng xác định.

## 15. Quy trình thiết kế list input

Khi thêm một list input vào Spring for GraphQL, hãy thực hiện theo thứ tự:

1. Xác định list chứa scalar, enum hay input object; chọn kiểu phần tử phù hợp.
2. Quyết định riêng nullability của list và từng phần tử.
3. Xác định ý nghĩa của field bị bỏ qua, `null` và list rỗng.
4. Khai báo input object nếu mỗi phần tử có nhiều thuộc tính liên quan.
5. Bind vào `List<T>` hoặc DTO/record có generic type rõ ràng.
6. Thêm validation cho số phần tử, định dạng, trùng lặp và ràng buộc nghiệp vụ.
7. Xác định quy tắc thứ tự, phần tử không tồn tại, transaction và partial success.
8. Đặt giới hạn tài nguyên và pagination phù hợp với quy mô dữ liệu.
9. Dùng `GraphQlTester` kiểm tra coercion, binding, lỗi và response thực tế.

List input giúp GraphQL API xử lý nhiều giá trị trong một operation với hợp đồng kiểu rõ ràng. Khi thiết kế đúng nullability, bảo toàn ngữ nghĩa của list và bind vào collection/DTO có kiểu, resolver Spring for GraphQL có thể xử lý dữ liệu theo lô một cách dễ kiểm soát. Hãy kết hợp validation, giới hạn kích thước và quy tắc nghiệp vụ để list input vừa tiện cho client vừa an toàn cho server.

## Tài liệu tham khảo

- [GraphQL Specification — List](https://spec.graphql.org/October2021/#sec-List)
- [GraphQL Specification — Input Coercion](https://spec.graphql.org/October2021/#sec-Input-Coercion)
- [Spring for GraphQL — Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.arguments)
- [Spring for GraphQL — Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.validation)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
