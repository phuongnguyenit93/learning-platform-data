# GraphQL schema trong ứng dụng Spring

Trong một ứng dụng Spring for GraphQL, schema là hợp đồng mô tả client có thể truy vấn dữ liệu nào, gửi arguments gì và nhận về những kiểu dữ liệu nào. Schema cũng là điểm nối giữa GraphQL API và các thành phần Java: một field được khai báo trong SDL có thể được phân giải bởi controller, một phương thức `@SchemaMapping`, một batch resolver hoặc cơ chế đọc thuộc tính mặc định của object nguồn.

Spring for GraphQL sử dụng GraphQL Java để thực thi schema và operation. Với Spring Boot, ứng dụng thường khai báo schema bằng **Schema Definition Language (SDL)** trong các tệp tài nguyên, sau đó dùng annotation của Spring để cung cấp dữ liệu cho các field. Cách tiếp cận này giúp cấu trúc API được thể hiện rõ ràng, độc lập với cách lưu trữ dữ liệu và cách tổ chức class Java.

Sau bài học, bạn có thể tổ chức tệp SDL trong ứng dụng Spring, định nghĩa root type và các kiểu dữ liệu, hiểu quy tắc nullable/list/input, nạp nhiều tệp schema, ánh xạ field vào controller và kiểm tra schema cùng resolver bằng `GraphQlTester`.

## 1. Schema giữ vai trò gì trong Spring for GraphQL?

Một GraphQL API có hai phần cần phối hợp:

- **Schema** mô tả hình dạng API: có những type nào, mỗi type có field gì, field nhận arguments nào, kiểu trả về ra sao và field nào cho phép `null`.
- **Data fetcher/resolver** cung cấp giá trị khi GraphQL thực thi một field. Trong Spring for GraphQL, resolver thường là method trong class `@Controller` được đánh dấu bằng `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping` hoặc `@BatchMapping`.

Ví dụ, schema có thể khai báo `Query.book(id: ID!): Book`. Khai báo này nói rằng client có thể gọi field `book` với một ID bắt buộc và nhận về một `Book` hoặc `null`. Nó chưa nói sách được lấy từ JPA, JDBC, REST service hay bộ nhớ. Phần triển khai resolver mới quyết định cách lấy dữ liệu.

Schema cũng không phải DTO Java được tự động sinh ra. Bạn có thể dùng record, class, interface hoặc kiểu domain hiện có làm object nguồn cho resolver, miễn là dữ liệu trả về tương thích với schema. Một schema tốt mô tả nhu cầu của client; mô hình Java và database có thể được thiết kế theo nhu cầu nội bộ của server.

## 2. Tạo dự án và đặt tệp schema

Với Spring Boot, thêm starter GraphQL và một web starter để cung cấp HTTP endpoint. Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Nếu ứng dụng dùng Spring WebFlux, có thể chọn `spring-boot-starter-webflux` thay cho `spring-boot-starter-web`. Phiên bản dependency thường được quản lý bởi Spring Boot dependency management; không nên tự ghim phiên bản GraphQL Java khác với phiên bản tương thích mà Boot quản lý nếu chưa có lý do cụ thể.

Spring Boot tự cấu hình `GraphQlSource` và endpoint HTTP khi phát hiện các dependency phù hợp. Theo cấu hình mặc định, schema được tìm trong `classpath:graphql/**/` với các phần mở rộng `.graphqls` và `.gqls`. Một cấu trúc dự án thường gặp:

```text
src/
├── main/
│   ├── java/com/example/library/
│   │   ├── LibraryApplication.java
│   │   └── graphql/
│   │       ├── BookGraphQlController.java
│   │       └── AuthorGraphQlController.java
│   └── resources/
│       ├── application.properties
│       └── graphql/
│           ├── book.graphqls
│           └── author.graphqls
└── test/
    └── java/com/example/library/
        └── BookGraphQlControllerTests.java
```

Có thể khai báo rõ vị trí schema và endpoint trong `application.properties`:

```properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
spring.graphql.path=/graphql

# Chỉ bật giao diện thử nghiệm trong môi trường phát triển.
spring.graphql.graphiql.enabled=true
```

Các giá trị đầu tiên tương ứng với vị trí và phần mở rộng tệp SDL. `spring.graphql.path` đặt URL nhận request GraphQL; `/graphql` là đường dẫn mặc định phổ biến. GraphiQL là giao diện hỗ trợ thử query trong môi trường phát triển, không nên bật tùy tiện ở môi trường production.

Khi ứng dụng chạy với cấu hình mặc định, client gửi HTTP request đến `/graphql`, thường dùng phương thức POST và body JSON có trường `query`, cùng `variables` nếu cần. Việc khai báo schema không tự tạo ra REST endpoint riêng cho từng type; các operation GraphQL đi qua endpoint GraphQL chung.

## 3. Định nghĩa root type và object type bằng SDL

GraphQL có ba root type tiêu chuẩn:

- `Query` mô tả các thao tác đọc dữ liệu.
- `Mutation` mô tả các thao tác thay đổi dữ liệu.
- `Subscription` mô tả các luồng sự kiện mà client đăng ký theo dõi.

Một schema nhỏ cho hệ thống thư viện có thể viết như sau:

```graphql
type Query {
  book(id: ID!): Book
  books(filter: BookFilter, first: Int = 20): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Subscription {
  bookCreated: Book!
}

type Book {
  id: ID!
  title: String!
  status: BookStatus!
  author: Author
}

type Author {
  id: ID!
  name: String!
}

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilter {
  keyword: String
  status: BookStatus
  authorId: ID
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
}
```

Trong SDL, `type Book` mô tả object có thể xuất hiện trong response. `Query.book` và `Query.books` là những field client có thể gọi để đọc dữ liệu. `Mutation.createBook` nhận một input object và trả về sách vừa tạo. `Subscription.bookCreated` mô tả payload của mỗi sự kiện sách mới.

Nếu root type sử dụng đúng tên mặc định `Query`, `Mutation` và `Subscription`, GraphQL có thể nhận diện chúng mà không cần khai báo `schema` block. Nếu muốn dùng tên root type khác, cần khai báo tường minh, ví dụ:

```graphql
schema {
  query: LibraryQuery
  mutation: LibraryMutation
}

type LibraryQuery {
  book(id: ID!): Book
}

type LibraryMutation {
  createBook(input: CreateBookInput!): Book!
}
```

Root query là thành phần bắt buộc của một schema GraphQL có thể thực thi. Mutation và Subscription là tùy chọn theo nhu cầu ứng dụng.

## 4. Hiểu scalar, enum và custom scalar

GraphQL định nghĩa sẵn một số scalar phổ biến:

| Scalar | Ý nghĩa |
| --- | --- |
| `Int` | Số nguyên có dấu 32 bit |
| `Float` | Số thực dấu phẩy động |
| `String` | Chuỗi ký tự UTF-8 |
| `Boolean` | Giá trị đúng hoặc sai |
| `ID` | Định danh, thường được truyền và trả về dưới dạng chuỗi |

`BookStatus` trong ví dụ là enum. Client chỉ được gửi một trong các giá trị `DRAFT`, `PUBLISHED` hoặc `ARCHIVED`. Enum giúp schema giới hạn miền giá trị thay vì nhận một chuỗi tùy ý. Khi ánh xạ sang Java, có thể dùng enum cùng tên để GraphQL Java chuyển đổi giá trị tương ứng.

Ngày tháng, thời gian, tiền tệ hoặc kiểu dữ liệu chuyên biệt không phải scalar tích hợp sẵn. Nếu API cần kiểu như `Date`, ứng dụng phải đăng ký custom scalar để định nghĩa cách parse input, serialize output và validate giá trị. Spring for GraphQL cho phép bổ sung cấu hình runtime bằng `RuntimeWiringConfigurer`. Có thể dùng scalar có sẵn từ thư viện mở rộng GraphQL Java hoặc tự triển khai `GraphQLScalarType` khi định dạng của ứng dụng có quy tắc riêng.

Ví dụ, nếu đã thêm thư viện `graphql-java-extended-scalars`, có thể đăng ký scalar ngày:

```java
@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.Date);
    }
}
```

Sau đó schema có thể khai báo field `publishedOn: Date`. Tên scalar trong SDL phải khớp tên scalar được đăng ký trong runtime wiring. Chỉ thêm khai báo `scalar Date` vào SDL là chưa đủ để GraphQL biết cách chuyển đổi giá trị ngày tháng.

## 5. Thiết kế kiểu nullable và danh sách

Trong GraphQL, field mặc định có thể nhận `null`. Dấu `!` biểu thị field non-null: resolver phải cung cấp giá trị khác `null` nếu operation thực thi field đó thành công.

Với danh sách, dấu `!` có thể áp dụng độc lập cho danh sách và từng phần tử:

| Kiểu | Danh sách có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| `[Book]` | Có | Có |
| `[Book]!` | Không | Có |
| `[Book!]` | Có | Không |
| `[Book!]!` | Không | Không |

Ví dụ `books: [Book!]!` yêu cầu resolver trả về một danh sách khác `null` và không có phần tử `null`. Danh sách rỗng `[]` vẫn hợp lệ. Trong khi đó, `book(id: ID!): Book` cho phép kết quả không tìm thấy là `null`.

Khi resolver trả `null` cho một field non-null, GraphQL tạo lỗi và lan truyền `null` lên field cha gần nhất có thể nhận null. Vì vậy, quyết định thêm `!` là một phần của thiết kế hợp đồng API, không chỉ là chú thích kiểu. Hãy dùng non-null khi ứng dụng có thể bảo đảm giá trị đó trong mọi trường hợp hợp lệ.

## 6. Phân biệt object type và input type

`type` mô tả dữ liệu server có thể trả về. `input` mô tả cấu trúc client được phép gửi vào arguments. Hai nhóm này không thể thay thế tùy ý cho nhau.

Ví dụ, `Book` là object type dùng trong response, còn `CreateBookInput` là input type dùng cho mutation:

```graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}

input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

Input object chỉ chứa scalar, enum hoặc input object khác, có thể kết hợp list và non-null. Nó không thể chứa một object output type như `Author` hay `Book`, và cũng không thể khai báo field có resolver như object type. Nếu cần tham chiếu một đối tượng đã tồn tại, thường truyền ID hoặc một input object chuyên biệt.

Trong Java, input object có thể được bind vào record hoặc class:

```java
public record CreateBookInput(
        String title,
        String authorId,
        BookStatus status) {
}
```

Spring for GraphQL hỗ trợ binding argument vào object Java. Tên field và kiểu trong input cần tương thích với constructor/property của class hoặc record. Nếu input lồng nhau, hãy thiết kế kiểu Java tương ứng và kiểm tra dữ liệu bắt buộc ở tầng phù hợp.

## 7. Ánh xạ root field vào controller Spring

Sau khi có SDL, controller cung cấp dữ liệu cho các root field. Spring for GraphQL dùng `@Controller` để phát hiện các method handler. Các annotation chuyên biệt cho biết method xử lý field thuộc root type nào.

```java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books(
            @Argument("filter") BookFilter filter,
            @Argument("first") Integer first) {
        return bookService.search(filter, first);
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

Vì tên method `book`, `books` và `createBook` trùng tên field trong schema, Spring có thể suy ra field cần ánh xạ. Có thể chỉ rõ tên khác trong annotation, ví dụ `@QueryMapping(name = "findBook")`, nếu tên method Java không trùng field SDL. `@Argument` lấy giá trị từ arguments của field; tên argument cần khớp với schema hoặc được chỉ định rõ trong annotation.

`@QueryMapping` tương ứng với field trên root `Query`, `@MutationMapping` tương ứng với root `Mutation`, còn `@SubscriptionMapping` tương ứng với root `Subscription`. Các annotation này là cách viết chuyên biệt, dễ đọc của việc khai báo `@SchemaMapping` trên root type tương ứng.

Ví dụ subscription có thể trả về một reactive stream:

```java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookCreated() {
        return eventService.bookCreated();
    }
}
```

`Flux<Book>` phát ra một `Book` cho mỗi sự kiện. Client cần dùng transport có hỗ trợ subscription và cấu hình tương ứng ở server. Việc chỉ khai báo `type Subscription` trong SDL không tự tạo nguồn sự kiện; resolver phải trả về publisher có thể phát dữ liệu.

## 8. Ánh xạ field lồng nhau bằng @SchemaMapping

Một object type thường có field tham chiếu đến object khác. Ví dụ `Book.author` trả về `Author`. Nếu field này không phải thuộc tính có sẵn trên object nguồn, hãy viết resolver cho nó bằng `@SchemaMapping`.

```java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

`typeName = "Book"` xác định object type trong SDL, còn `field = "author"` xác định field cần phân giải. Tham số `Book book` là source object mà resolver nhận được từ field cha. Giá trị trả về phải tương thích với kiểu `Author` trong schema.

Nếu DTO `Book` đã có thuộc tính hoặc getter `author` phù hợp, GraphQL Java có thể dùng property data fetcher mặc định để đọc giá trị đó mà không cần method `@SchemaMapping`. Hãy viết resolver riêng khi cần tính toán, gọi service khác, kiểm soát việc tải dữ liệu hoặc chuyển đổi mô hình.

### Gom việc phân giải field bằng @BatchMapping

Khi query trả về nhiều sách và mỗi sách cần field `author`, một resolver đơn giản có thể gọi service lấy tác giả riêng cho từng sách. Nếu mỗi lần gọi phát sinh một truy vấn database, số truy vấn tăng theo số sách và tạo ra vấn đề N+1.

`@BatchMapping` cho phép Spring for GraphQL gom các source object rồi phân giải field theo lô. Ví dụ:

```java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        Set<String> authorIds = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds);

        return books.stream().collect(Collectors.toMap(
                Function.identity(),
                book -> authorsById.get(book.authorId())
        ));
    }
}
```

Ví dụ giả định service trả về map tác giả theo ID. Trong ứng dụng thực tế, cần quyết định cách xử lý ID không tìm thấy và bảo đảm key của map khớp source object. Có thể dùng `@BatchMapping` thay cho resolver `@SchemaMapping` đơn lẻ cho cùng field; không nên đăng ký hai resolver cạnh tranh cho cùng một field.

Schema vẫn khai báo `Book.author` như một field bình thường. Cơ chế batching là chi tiết triển khai phía server, client không cần biết field được phân giải theo từng object hay theo lô.

## 9. Chia schema thành nhiều tệp

Khi API lớn dần, có thể tách schema theo domain hoặc nhóm chức năng, ví dụ `book.graphqls`, `author.graphqls`, `review.graphqls`. Spring Boot tìm các tệp trong schema locations và GraphQL Java xây dựng một schema thống nhất từ các định nghĩa đó.

Nếu một tệp đã khai báo `type Query`, tệp khác muốn bổ sung field cho Query nên dùng `extend type Query`:

```graphql
# book.graphqls
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
}
```

```graphql
# author.graphqls
extend type Query {
  author(id: ID!): Author
  authors: [Author!]!
}

type Author {
  id: ID!
  name: String!
}
```

`extend type Query` mở rộng root type đã tồn tại. Nếu khai báo `type Query` lần nữa với mục đích định nghĩa mới thay vì extension, schema có thể gặp lỗi định nghĩa trùng lặp. Tên type, field, argument và enum value phải nhất quán trên tất cả tệp được nạp.

Việc chia tệp giúp quản lý source dễ hơn, nhưng client vẫn nhìn thấy một schema API thống nhất. Tên file không tạo namespace GraphQL; hai tệp cùng định nghĩa `Book` không trở thành hai type khác nhau chỉ vì nằm ở file khác nhau.

## 10. Bổ sung runtime wiring khi schema cần cấu hình đặc biệt

SDL mô tả type và field, nhưng một số kiểu cần hành vi runtime để chuyển đổi hoặc xác định kiểu cụ thể. Spring for GraphQL cung cấp `RuntimeWiringConfigurer` để bổ sung cấu hình cho GraphQL Java, chẳng hạn custom scalar, type resolver cho interface/union hoặc data fetcher đặc biệt.

Ví dụ custom scalar `Date` ở phần trước được đăng ký qua `RuntimeWiringConfigurer`. Với interface hoặc union, GraphQL cần xác định object type cụ thể khi resolver trả về một instance. Nếu quy tắc nhận diện mặc định không đủ, có thể đăng ký `TypeResolver` phù hợp trong runtime wiring.

Không nên đưa logic nghiệp vụ lớn vào runtime wiring. Các thao tác đọc/ghi dữ liệu, kiểm tra quyền hoặc gọi dịch vụ thường thuộc controller, service hay thành phần chuyên biệt. Runtime wiring phù hợp với cấu hình thực thi ở cấp schema.

## 11. Kiểm tra schema và resolver bằng GraphQlTester

Sau khi schema được nạp và controller được đăng ký, nên kiểm tra operation thật thay vì chỉ kiểm tra method Java riêng lẻ. `GraphQlTester` cho phép gửi GraphQL document, truyền variables và kiểm tra response theo đường dẫn field.

```java
@GraphQlTest(BookGraphQlController.class)
class BookGraphQlControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void returnsBookById() {
        given(bookService.findById("book-42"))
                .willReturn(new Book("book-42", "GraphQL nhập môn"));

        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
                .variable("id", "book-42")
                .execute()
                .path("book.id")
                .entity(String.class)
                .isEqualTo("book-42");
    }
}
```

Đây là ví dụ rút gọn; kiểu `Book`, constructor và cấu hình mock cần khớp với ứng dụng thực tế. `@GraphQlTest` tập trung vào thành phần GraphQL và các controller được chỉ định. Nếu muốn kiểm tra toàn bộ cấu hình ứng dụng, schema, transport và security chain, có thể dùng `@SpringBootTest` kết hợp tester phù hợp.

Nên có test cho các trường hợp sau:

- Query hợp lệ trả về đúng field và kiểu dữ liệu.
- Argument bắt buộc bị thiếu hoặc có kiểu không hợp lệ.
- Mutation nhận input object và trả về kết quả mong đợi.
- Field lồng nhau được phân giải đúng, bao gồm resolver batch nếu có.
- Field nullable trả `null` đúng hợp đồng; field non-null không bị trả `null` ngoài dự kiến.
- Lỗi resolver được biểu diễn đúng trong phần `errors` của response.

## 12. Lỗi thường gặp khi tích hợp schema với Spring

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy schema hoặc schema rỗng | Đặt file sai thư mục, sai phần mở rộng hoặc cấu hình schema locations không khớp | Kiểm tra `src/main/resources/graphql/`, `spring.graphql.schema.locations` và `spring.graphql.schema.file-extensions` |
| Lỗi parse hoặc validation khi khởi động | SDL sai cú pháp, tham chiếu type không tồn tại hoặc khai báo trùng | Đọc lỗi schema, kiểm tra type/field và các tệp `extend` |
| `Cannot query field ...` | Query gọi field không có trên type trong schema | So sánh document với SDL đang được nạp |
| Resolver không được gọi | Sai root type, tên field hoặc `typeName` trong mapping | Đối chiếu `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` với SDL |
| Argument nhận `null` | Sai tên argument, kiểu không tương thích hoặc client không gửi biến | Kiểm tra `@Argument`, tên trong SDL và payload variables |
| Field object trả `null` ngoài dự kiến | Property fetcher không tìm thấy thuộc tính hoặc resolver không trả dữ liệu | Kiểm tra getter/property của source object và mapping method |
| Custom scalar không parse được | Scalar chỉ được khai báo trong SDL mà chưa đăng ký coercing/runtime wiring | Đăng ký scalar phù hợp và kiểm tra định dạng input/output |
| Schema bị lỗi khi tách nhiều file | Nhiều file định nghĩa lại cùng type thay vì mở rộng type hiện có | Dùng `extend type` và tránh định nghĩa field trùng |

## 13. Nguyên tắc thiết kế schema cho ứng dụng Spring

- Thiết kế schema theo ngôn ngữ nghiệp vụ và nhu cầu client. Không để cấu trúc bảng database quyết định trực tiếp toàn bộ API.
- Dùng `input` riêng cho dữ liệu ghi và filter. Không tái sử dụng output type làm input chỉ để giảm số dòng SDL.
- Chọn nullable/non-null dựa trên bảo đảm dữ liệu thật của hệ thống. Thay đổi một field từ nullable sang non-null có thể ảnh hưởng client hiện tại.
- Đặt tên field và argument nhất quán. Dùng alias ở client khi cần tên response khác, thay vì tạo nhiều field server chỉ để phục vụ cách đặt tên của một màn hình.
- Chia SDL thành nhiều file theo domain khi cần, nhưng duy trì một schema hợp nhất và dùng `extend type` để bổ sung root field.
- Giữ resolver mỏng: nhận argument, gọi service phù hợp và trả kết quả. Quy tắc nghiệp vụ nên ở service/domain layer.
- Quan sát số lần resolver được gọi. Dùng `@BatchMapping` hoặc DataLoader khi field lồng nhau có nguy cơ tạo N+1.
- Bảo vệ dữ liệu ở server. Việc một field xuất hiện trong schema không có nghĩa mọi người dùng đều được phép đọc hoặc thay đổi field đó; cần xác thực và phân quyền ở cấp operation/field phù hợp.
- Kiểm thử schema và response bằng operation đại diện cho client, đặc biệt khi thêm field, đổi nullability hoặc thay đổi input type.

## 14. Bài tập thực hành

Hãy mở rộng API thư viện theo yêu cầu sau:

1. Tạo `book.graphqls` với `Query.book`, `Query.books`, `Mutation.createBook`, `Book`, `Author`, `BookStatus` và các input type cần thiết.
2. Tách khai báo tác giả sang `author.graphqls`, dùng `extend type Query` để thêm `author(id: ID!): Author`.
3. Viết `@QueryMapping` cho truy vấn sách và `@MutationMapping` cho thao tác tạo sách.
4. Viết `@SchemaMapping` cho `Book.author`. Sau đó thay bằng `@BatchMapping` khi query danh sách có nhiều sách để giảm số lần gọi service.
5. Viết test `GraphQlTester` cho query lấy sách, query lấy danh sách và mutation tạo sách.

Một phần SDL cốt lõi có thể bắt đầu như sau:

```graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

input CreateBookInput {
  title: String!
  authorId: ID!
}
```

Khi hoàn thành, hãy kiểm tra rằng mỗi field trong operation đều tồn tại trong schema, mỗi root field có handler hoặc property fetcher phù hợp, các input được bind đúng kiểu Java và response tuân thủ nullability đã khai báo. Đây là nền tảng để tiếp tục học xử lý lỗi, bảo mật theo field, DataLoader và tối ưu truy vấn trong Spring for GraphQL.
