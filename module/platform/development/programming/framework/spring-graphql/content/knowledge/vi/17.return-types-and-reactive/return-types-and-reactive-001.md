# Java object làm GraphQL result

Trong Spring for GraphQL, một resolver có thể trả về Java object để GraphQL runtime tạo kết quả cho một object type trong schema. Ví dụ, query `book(id: ...)` có thể trả về một đối tượng `BookView`; client sau đó chọn `id`, `title`, `author` hoặc các field khác của object đó.

Điểm cần hiểu là Java object không được trả thẳng thành một khối JSON cố định. GraphQL runtime đọc selection set của client và resolve từng field trên object nguồn. Các field có thể được lấy từ thuộc tính Java theo cơ chế mặc định, hoặc dùng resolver riêng với `@SchemaMapping` khi cần truy vấn dữ liệu, tính toán hay kiểm tra quyền.

## 1. Java object và GraphQL object type

GraphQL SDL định nghĩa cấu trúc dữ liệu đầu ra. Ví dụ:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
    publishedYear: Int
}
```

`Query.book` trả về `Book` hoặc `null`. Nếu tìm thấy sách, resolver có thể trả một Java object mang dữ liệu tương ứng. `Book` trong SDL là hợp đồng API; class Java là một cách biểu diễn dữ liệu nội bộ để cung cấp kết quả cho hợp đồng đó.

Tên class Java không bắt buộc giống tên GraphQL type. Tuy nhiên, các field GraphQL cần có cách resolve tương ứng. Với field được xử lý mặc định, tên property Java thường cần khớp tên field trong SDL. Với field có tên hoặc nguồn dữ liệu khác, có thể khai báo resolver rõ ràng.

## 2. Trả Java object từ @QueryMapping

Ví dụ một DTO JavaBean đơn giản:

```java
package com.example.graphql.book;

public class BookView {

    private final String id;
    private final String title;
    private final String description;
    private final Integer publishedYear;
    private final String authorId;

    public BookView(
            String id,
            String title,
            String description,
            Integer publishedYear,
            String authorId) {
        this.id = id;
        this.title = title;
        this.description = description;
        this.publishedYear = publishedYear;
        this.authorId = authorId;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getDescription() {
        return description;
    }

    public Integer getPublishedYear() {
        return publishedYear;
    }

    public String getAuthorId() {
        return authorId;
    }
}
```

Controller trả về object:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(@Argument("id") String id) {
        return bookService.findViewById(id);
    }
}
```

Method `book` được ánh xạ vào `Query.book`. Giá trị trả về là một `BookView`; GraphQL runtime tiếp tục resolve các field mà client đã chọn trên object này.

## 3. PropertyDataFetcher đọc thuộc tính Java

Với field không có resolver tùy chỉnh, GraphQL Java thường dùng property data fetcher mặc định (`PropertyDataFetcher`) để đọc giá trị từ object nguồn. Với JavaBean, cơ chế này có thể đọc thông qua getter như `getTitle()` hoặc `isAvailable()`; với một `Map`, giá trị có thể được lấy theo key trùng tên field.

Ví dụ client gửi:

```graphql
query BookSummary($id: ID!) {
    book(id: $id) {
        id
        title
        publishedYear
    }
}
```

Khi `BookView` là object nguồn:

- GraphQL field `id` được resolve từ thuộc tính `id`.
- GraphQL field `title` được resolve từ thuộc tính `title`.
- GraphQL field `publishedYear` được resolve từ thuộc tính `publishedYear`.

Không cần viết ba method `@SchemaMapping` chỉ để trả lại các giá trị đã có sẵn trên DTO. Resolver mặc định giúp giảm code lặp và giữ các field đơn giản dễ đọc.

Tên field phải tương thích với cách truy cập thuộc tính. Nếu Java model dùng `bookName` trong khi schema công bố `title`, property fetcher không tự biết hai tên này có cùng ý nghĩa. Hãy dùng DTO có tên property phù hợp hoặc khai báo mapping tường minh.

## 4. Field có tên khác hoặc cần logic riêng

Khi GraphQL field không thể đọc trực tiếp từ object nguồn, dùng `@SchemaMapping` để cung cấp resolver.

Ví dụ `BookEntity` chỉ lưu `authorId`, trong khi schema muốn trả về một object `Author`:

```graphql
type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Resolver:

```java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public AuthorView author(BookView book) {
        return authorService.findViewById(book.getAuthorId());
    }
}
```

`@SchemaMapping` nối field `Book.author` với method `author`; method nhận object cha làm source và trả về một Java object `AuthorView` cho field con.

Có thể dùng method-level mapping khi field cần gọi service, ghép nhiều nguồn dữ liệu, áp dụng quy tắc quyền hoặc chuyển đổi dữ liệu. Không cần viết resolver cho mọi thuộc tính nếu property fetcher mặc định đã đáp ứng.

## 5. Object lồng nhau và selection set

Một Java object có thể chứa object khác. Ví dụ DTO:

```java
public class BookView {
    private String id;
    private String title;
    private AuthorView author;

    public String getId() { return id; }
    public String getTitle() { return title; }
    public AuthorView getAuthor() { return author; }
}

public class AuthorView {
    private String id;
    private String name;

    public String getId() { return id; }
    public String getName() { return name; }
}
```

Nếu `BookView.author` đã chứa `AuthorView`, GraphQL có thể resolve field lồng nhau bằng property fetcher mặc định:

```graphql
query {
    book(id: "book-42") {
        title
        author {
            id
            name
        }
    }
}
```

Runtime resolve `Query.book` trước, rồi resolve `Book.title` và `Book.author`. Với object `AuthorView`, nó tiếp tục resolve `Author.id` và `Author.name` theo selection set.

Nếu `author` chưa có sẵn trên object cha, dùng `@SchemaMapping` như phần trước. Dù object lồng nhau được lấy từ DTO hay resolver riêng, kiểu dữ liệu trả về phải tương thích với kiểu GraphQL đã khai báo.

## 6. Trả về collection Java

GraphQL list thường được cung cấp bằng một collection Java như `List<T>`, hoặc một kiểu iterable/array mà GraphQL Java hỗ trợ. Ví dụ:

```graphql
type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
```

Resolver:

```java
@QueryMapping
public List<BookView> booksByAuthor(@Argument("authorId") String authorId) {
    return bookService.findViewsByAuthorId(authorId);
}
```

Client chọn field của từng phần tử:

```graphql
query {
    booksByAuthor(authorId: "author-7") {
        id
        title
    }
}
```

Kiểu `[Book!]!` cam kết danh sách không null và từng phần tử không null. Danh sách rỗng `[]` vẫn là một kết quả hợp lệ. Nếu Java collection chứa phần tử null, kết quả sẽ vi phạm nullability của phần tử và GraphQL có thể phát sinh execution error cùng cơ chế lan truyền null.

Với danh sách lớn, hãy thiết kế phân trang và giới hạn số phần tử. Trả toàn bộ collection không giới hạn có thể làm tăng bộ nhớ, thời gian truy vấn và kích thước response.

## 7. Java Map làm GraphQL result

Trong một số trường hợp, resolver có thể trả `Map<String, Object>` thay cho DTO. Property fetcher có thể đọc giá trị theo key tương ứng với GraphQL field.

Ví dụ:

```java
@QueryMapping
public Map<String, Object> dashboard() {
    return Map.of(
        "activeUsers", 125,
        "openOrders", 18,
        "status", "HEALTHY"
    );
}
```

SDL tương ứng:

```graphql
type Query {
    dashboard: Dashboard!
}

type Dashboard {
    activeUsers: Int!
    openOrders: Int!
    status: String!
}
```

Các key trong map phải tương ứng với field mà schema công bố. Nếu thiếu key hoặc giá trị không đúng kiểu, field có thể trả null hoặc gây lỗi coercion/nullability tùy trường hợp.

Map linh hoạt, hữu ích cho kết quả tổng hợp hoặc cấu trúc thay đổi. Tuy nhiên, DTO thường dễ bảo trì hơn với hợp đồng ổn định vì compiler có thể hỗ trợ kiểm tra kiểu và IDE có thể điều hướng property. Không nên dùng map tùy tiện cho mọi domain object vì lỗi chính tả tên key chỉ xuất hiện khi query được thực thi.

## 8. Kiểu Java và GraphQL scalar

Các property scalar trong Java cần có cách coercion phù hợp với scalar trong SDL.

| GraphQL scalar | Kiểu Java thường dùng | Lưu ý |
| --- | --- | --- |
| `String` | `String` | Không tự chuyển object tùy ý thành chuỗi API |
| `Boolean` | `Boolean` hoặc `boolean` | Wrapper `Boolean` có thể null; primitive không thể null |
| `Int` | `Integer` hoặc `int` | GraphQL `Int` là signed 32-bit integer |
| `Float` | `Double`, `Float` hoặc kiểu số được hỗ trợ | Xác định rõ độ chính xác và cách chuyển đổi |
| `ID` | Thường là `String` | Dùng cho định danh, không phải số học |
| `enum` | Java `enum` tương ứng | Tên/value cần được ánh xạ phù hợp |

Ngày tháng, thời điểm, tiền tệ hoặc kiểu domain đặc biệt thường cần custom scalar hay một kiểu biểu diễn API rõ ràng. Ví dụ `LocalDate` không tự trở thành GraphQL scalar tích hợp sẵn trong mọi cấu hình; ứng dụng cần đăng ký scalar có coercing phù hợp hoặc chuyển sang chuỗi theo định dạng đã thống nhất.

Không nên mặc định Jackson JSON serializer quyết định toàn bộ mapping GraphQL field. GraphQL runtime dùng schema, data fetcher và scalar coercing để resolve và serialize từng field theo hợp đồng GraphQL.

## 9. Nullability giữa Java và GraphQL

Java và GraphQL có cách biểu diễn nullability khác nhau. Trong SDL, dấu `!` là cam kết của API:

```graphql
type Book {
    id: ID!
    title: String!
    description: String
}
```

Java `String` có thể null dù field GraphQL được khai báo `String!`. Nếu getter trả null cho `title`, GraphQL sẽ tạo execution error và lan truyền null lên field cha gần nhất có thể nhận null. Vì vậy, cần bảo đảm DTO đáp ứng cam kết non-null của schema.

Với Java primitive như `int` hoặc `boolean`, giá trị không thể null và có thể phù hợp khi API luôn có giá trị mặc định. Tuy nhiên, primitive có thể che mất khác biệt giữa "không có dữ liệu" và giá trị mặc định như `0` hoặc `false`. Dùng wrapper `Integer` hoặc `Boolean` khi null là trạng thái có ý nghĩa và SDL cho phép.

Ví dụ:

| Java property | SDL | Ý nghĩa |
| --- | --- | --- |
| `String title` | `title: String!` | Getter phải luôn trả chuỗi khác null |
| `String description` | `description: String` | Có thể trả null |
| `Integer publishedYear` | `publishedYear: Int` | Có thể chưa có năm xuất bản |
| `int pageCount` | `pageCount: Int!` | Luôn có giá trị số nguyên |

Schema nên phản ánh khả năng thực tế của dữ liệu và quy tắc nghiệp vụ, không nên gắn `!` chỉ vì muốn response trông đầy đủ.

## 10. DTO hay JPA entity làm GraphQL result?

Có thể trả trực tiếp JPA entity nếu cấu trúc và vòng đời của entity phù hợp với API. Tuy nhiên, với ứng dụng có domain model phức tạp, DTO thường giúp kiểm soát hợp đồng GraphQL tốt hơn.

| Tiêu chí | Trả JPA entity | Trả DTO/View model |
| --- | --- | --- |
| Tốc độ triển khai ban đầu | Có thể nhanh khi cấu trúc đơn giản | Cần bước chuyển đổi |
| Kiểm soát field công khai | Dễ vô tình phụ thuộc vào entity | Chọn rõ field cần công bố |
| Lazy loading | Có thể phát sinh truy vấn khi resolve field | Có thể chuẩn bị dữ liệu theo use case |
| Quan hệ vòng/cyclic | Có thể tạo selection sâu hoặc logic khó kiểm soát | Có thể định hình response có chủ đích |
| Tách domain và API | Gắn hợp đồng API với persistence model | API độc lập hơn với schema database |

DTO không tự giải quyết N+1. Nếu service tạo DTO bằng cách tải từng quan hệ riêng lẻ, vấn đề vẫn tồn tại. Hãy dùng projection, fetch plan, batch loading hoặc DataLoader theo nhu cầu truy vấn.

Đặc biệt, không nên trả entity có các thuộc tính nhạy cảm chỉ vì client hiện tại chưa chọn chúng. Chỉ những field được khai báo trong schema mới có thể được client query, nhưng khi schema mở rộng, property fetcher có thể làm lộ dữ liệu nếu entity được dùng trực tiếp mà không rà soát quyền và field mới.

## 11. Interface và Union khi Java result có nhiều kiểu cụ thể

Một field GraphQL có thể trả về interface hoặc union, trong khi Java resolver trả các object thuộc nhiều class khác nhau.

Ví dụ SDL:

```graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    author: String!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

Resolver có thể trả danh sách chứa `BookView` và `ArticleView`, nhưng GraphQL runtime cần biết object type cụ thể của từng phần tử. Khi đó, cần cấu hình type resolution phù hợp, chẳng hạn `TypeResolver` thông qua `RuntimeWiringConfigurer`, để ánh xạ Java implementation sang GraphQL object type.

```java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return builder -> builder.type("SearchResult", wiring ->
        wiring.typeResolver(environment -> {
            Object source = environment.getObject();
            if (source instanceof BookView) {
                return environment.getSchema().getObjectType("Book");
            }
            if (source instanceof ArticleView) {
                return environment.getSchema().getObjectType("Article");
            }
            throw new IllegalStateException("Unsupported search result type");
        })
    );
}
```

Ví dụ trên minh họa nguyên tắc ánh xạ. Trong code thực tế, cần xử lý rõ trường hợp source null và bảo đảm mọi implementation có thể xuất hiện đều được đăng ký. Nếu chỉ trả một object type cụ thể như `Book`, không cần type resolver đa hình.

## 12. Kết quả object bất đồng bộ

Resolver có thể trả object trực tiếp hoặc một kiểu bất đồng bộ được Spring for GraphQL hỗ trợ. Ví dụ:

```java
@QueryMapping
public CompletableFuture<BookView> book(@Argument("id") String id) {
    return bookService.findViewByIdAsync(id);
}
```

Với ứng dụng reactive, method có thể trả về `Mono<BookView>` khi sử dụng stack và dependency tương ứng. Dù kết quả được cung cấp đồng bộ hay bất đồng bộ, sau khi có object, GraphQL vẫn resolve các field theo selection set như bình thường.

Không bọc một lời gọi blocking vào `CompletableFuture` chỉ để làm method trông bất đồng bộ. Cần xem xét thread pool, I/O thực tế và cách service truy cập dữ liệu. Kiểu wrapper không thay đổi hợp đồng GraphQL object type mà nó đại diện.

## 13. Kiểm thử Java object làm GraphQL result

`GraphQlTester` cho phép thực thi query và kiểm tra field lấy từ Java object:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookQueryController.class)
class BookQueryControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void mapsJavaObjectPropertiesToGraphQlFields() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL thực hành");
    }
}
```

Ví dụ giả định test context cung cấp `BookService` mock hoặc test bean trả `BookView` có ID `book-42` và tiêu đề như mong đợi. Test này kiểm tra cả root mapping và việc GraphQL đọc property từ Java object.

Nên bổ sung test cho:

- Field JavaBean được resolve bằng getter.
- Property không tồn tại hoặc tên không khớp schema.
- Nested object và collection.
- Null ở field nullable và vi phạm field non-null.
- Map result với key tương ứng.
- Custom scalar và enum coercion.
- Interface/union với từng concrete implementation.
- Resolver bất đồng bộ và lỗi phát sinh khi hoàn tất future/publisher.

Với integration test, kiểm tra cả database projection, lazy loading, security và transaction để biết object trả về có đáp ứng đúng hợp đồng và hiệu năng hay không.

## 14. Lỗi thường gặp khi trả Java object

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field trả null dù object có dữ liệu | Getter hoặc tên property không khớp field | Kiểm tra accessor và dùng `@SchemaMapping` khi cần |
| Field object không query được | Client thiếu selection set | Chọn field con trong query |
| Non-null execution error | Java property trả null nhưng SDL khai báo `!` | Sửa dữ liệu hoặc điều chỉnh nullability đúng nghiệp vụ |
| Scalar coercion error | Kiểu Java không tương thích scalar | Dùng kiểu phù hợp hoặc custom scalar |
| Nested field phát sinh nhiều truy vấn | Lazy loading hoặc resolver riêng theo từng parent | Dùng projection, `@BatchMapping` hoặc DataLoader |
| Map thiếu key | Tên key không khớp field hoặc dữ liệu không đầy đủ | Chuẩn hóa key hoặc dùng DTO có kiểu |
| Interface không resolve được | Chưa xác định concrete GraphQL type | Đăng ký `TypeResolver` hoặc `isTypeOf` phù hợp |
| API lộ field ngoài ý muốn khi schema mở rộng | Trả trực tiếp entity mà không rà soát property | Dùng DTO và kiểm soát field/authorization |

## 15. Checklist thiết kế Java result type

- Java object có cung cấp đủ dữ liệu cho GraphQL object type?
- Property name và accessor có tương thích với field trong SDL?
- Field cần logic riêng đã có `@SchemaMapping` phù hợp?
- Nested object và collection có nullability đúng với schema?
- Java type có coercion phù hợp với scalar và enum?
- Đã chọn DTO hay entity dựa trên ranh giới API, quyền và persistence?
- Có nguy cơ lazy loading hoặc N+1 khi resolve field con không?
- Interface/union đã có type resolver cho mọi implementation chưa?
- Kiểu bất đồng bộ có phản ánh I/O thực tế và được hỗ trợ bởi stack đang dùng?
- Test đã kiểm tra response, nullability và lỗi coercion?

Java object làm GraphQL result là cách phổ biến để nối dữ liệu của ứng dụng Spring với object type trong schema. `@QueryMapping` hoặc `@SchemaMapping` trả object nguồn; GraphQL runtime đọc selection set và resolve từng field bằng property fetcher mặc định hoặc data fetcher tùy chỉnh. Chọn DTO có accessor rõ ràng, thiết kế nullability chính xác, xử lý nested object có chủ đích và kiểm soát truy vấn dữ liệu giúp API dễ bảo trì, an toàn và có hiệu năng ổn định.
