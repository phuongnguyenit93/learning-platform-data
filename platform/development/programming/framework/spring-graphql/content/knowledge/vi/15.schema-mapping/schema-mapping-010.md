# Class-level @SchemaMapping

Trong Spring for GraphQL, `@SchemaMapping` thường được đặt trên method để ánh xạ method Java vào một field của GraphQL object type. Khi một controller có nhiều resolver cùng xử lý field của một GraphQL type, có thể đặt `@SchemaMapping(typeName = "...")` ở cấp class để khai báo type mặc định dùng chung cho các method mapping bên trong controller.

Cách tổ chức này giúp nhóm các resolver theo GraphQL type. Ví dụ, một `BookController` có thể xử lý `Book.author`, `Book.publisher` và `Book.reviews`; tên type `Book` chỉ cần khai báo một lần ở class. Các method vẫn phải có annotation mapping riêng để chỉ rõ field cần xử lý.

## 1. Class-level @SchemaMapping là gì?

`@SchemaMapping` có thể được dùng ở hai cấp:

- **Cấp method**: xác định field cụ thể cần ánh xạ và có thể chỉ định GraphQL type chứa field đó.
- **Cấp class**: cung cấp `typeName` mặc định cho các handler method trong controller.

Ví dụ:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        // Resolve Book.author
    }

    @SchemaMapping
    public Publisher publisher(Book book) {
        // Resolve Book.publisher
    }
}
```

Hai method đều được ánh xạ vào field của GraphQL type `Book`. Ở đây, `typeName = "Book"` trên class là giá trị mặc định; `field` được suy ra từ tên method (`author` và `publisher`).

Điều quan trọng: annotation ở cấp class không tự biến mọi method trong class thành resolver. Mỗi handler method vẫn cần annotation mapping phù hợp, chẳng hạn `@SchemaMapping` hoặc `@BatchMapping`. Annotation class-level chỉ giúp chia sẻ cấu hình type, không khai báo field và không thay thế method-level mapping.

## 2. Chuẩn bị GraphQL schema

Giả sử ứng dụng thư viện có schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
    publisher: Publisher
    reviewCount: Int!
}

type Author {
    id: ID!
    name: String!
}

type Publisher {
    id: ID!
    name: String!
}
```

`Book` có ba field cần logic lấy dữ liệu riêng: `author`, `publisher` và `reviewCount`. Những field như `id` và `title` có thể được đọc trực tiếp từ object nguồn bằng property data fetcher mặc định nếu Java object cung cấp accessor tương ứng.

Ví dụ Java record cho object nguồn:

```java
public record Book(
    String id,
    String title,
    String authorId,
    String publisherId
) {}
```

Không nhất thiết phải viết `@SchemaMapping` cho mọi field. Chỉ tạo resolver khi field cần truy vấn nguồn dữ liệu khác, tính toán, kiểm tra quyền hoặc xử lý logic riêng.

## 3. Khai báo type mặc định trên controller

Controller được đăng ký như một Spring bean bằng `@Controller`. `@SchemaMapping(typeName = "Book")` ở cấp class khai báo GraphQL type mặc định cho các method handler phù hợp:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final PublisherService publisherService;

    public BookController(
            AuthorService authorService,
            PublisherService publisherService) {
        this.authorService = authorService;
        this.publisherService = publisherService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping
    public Publisher publisher(Book book) {
        return publisherService.findById(book.publisherId());
    }
}
```

Spring for GraphQL đọc annotation class-level, sau đó dùng `Book` làm type mặc định khi đăng ký các method `@SchemaMapping` trong controller. Mỗi method nhận `Book` làm source/parent object và trả về dữ liệu cho field tương ứng.

`@Controller` và `@SchemaMapping` có vai trò khác nhau. `@Controller` đưa class vào Spring application context; `@SchemaMapping` cung cấp metadata để Spring for GraphQL đăng ký handler method. Nếu class không được component scan hoặc không được đăng ký thành bean, configurer không thể phát hiện các mapping của nó.

## 4. Suy ra tên field từ method và khai báo tường minh

Khi method-level `@SchemaMapping` không chỉ định `field`, Spring sử dụng tên method làm tên GraphQL field.

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book source) {
        return authorService.findById(source.authorId());
    }
}
```

Method `author` ánh xạ tới `Book.author`. Tên tham số `source` không ảnh hưởng tới tên field; kiểu tham số `Book` biểu diễn source object.

Nếu tên method khác tên field trong SDL, đặt `field` trên method:

```java
@SchemaMapping(field = "reviewCount")
public Integer countReviews(Book book) {
    return reviewService.countByBookId(book.id());
}
```

Class-level annotation cung cấp `typeName = "Book"`, còn method-level annotation xác định field `reviewCount`. Việc tách hai giá trị giúp tên method Java có thể diễn đạt ý định trong code mà vẫn ánh xạ đúng hợp đồng GraphQL.

Có thể khai báo cả type và field trên method nếu muốn mapping tường minh hoặc cần ghi đè type mặc định:

```java
@SchemaMapping(typeName = "Magazine", field = "reviewCount")
public Integer countMagazineReviews(Magazine magazine) {
    return reviewService.countByMagazineId(magazine.id());
}
```

Trong trường hợp này, method-level `typeName` xác định type cụ thể cho mapping đó. Hãy dùng override khi method thực sự thuộc một GraphQL type khác; nếu controller đang chứa nhiều nhóm type không liên quan, nên cân nhắc tách controller để giữ ranh giới dễ hiểu.

## 5. Truyền argument cho field mapping

Field của object type có thể nhận argument giống field trên root type. `@Argument` lấy giá trị từ argument của field đang được resolve.

SDL:

```graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
```

Resolver:

```java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument("first") Integer first) {
    return reviewService.findFirstByBookId(book.id(), first);
}
```

Do class-level `typeName` là `Book`, method trên ánh xạ tới `Book.reviews`. `Book book` là source object; `@Argument("first")` nhận argument `first` do client truyền. Nên chỉ định tên argument tường minh nếu không muốn phụ thuộc metadata tên parameter của Java.

Client có thể gọi:

```graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 5) {
            id
            rating
            comment
        }
    }
}
```

Class-level `@SchemaMapping` không làm thay đổi cách truyền argument. Nó chỉ cung cấp type mặc định; method handler vẫn nhận source object và argument theo cơ chế phân giải tham số của Spring for GraphQL.

## 6. Tách resolver theo GraphQL type

Class-level mapping hữu ích nhất khi các method trong controller cùng xử lý một GraphQL type và cùng thuộc một phần nghiệp vụ. Không nên gom mọi resolver của toàn API vào một class chỉ để giảm số file.

Ví dụ có thể tổ chức:

```text
graphql/
└── book/
    ├── BookQueryController.java
    ├── BookController.java
    ├── AuthorController.java
    └── ReviewController.java
```

- `BookQueryController` xử lý root field như `Query.book`.
- `BookController` dùng `@SchemaMapping(typeName = "Book")` cho field của Book.
- `AuthorController` dùng `@SchemaMapping(typeName = "Author")` cho field của Author.
- `ReviewController` xử lý field thuộc Review nếu cần logic riêng.

Ví dụ controller riêng cho Author:

```java
@Controller
@SchemaMapping(typeName = "Author")
public class AuthorController {

    private final BookService bookService;

    public AuthorController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
```

Method `books` ánh xạ tới `Author.books`, vì type mặc định của controller là `Author`. Nhờ vậy, mỗi controller tập trung vào field của một type và dễ kiểm tra khi schema thay đổi.

## 7. Phân biệt class-level @SchemaMapping với @QueryMapping

`@SchemaMapping` cấp class thường dùng để chia sẻ type chứa field cho các resolver của object type, ví dụ `Book.author` hoặc `Author.books`. Root operation có mapping riêng:

- `@QueryMapping` ánh xạ vào root type `Query`.
- `@MutationMapping` ánh xạ vào root type `Mutation`.
- `@SubscriptionMapping` ánh xạ vào root type `Subscription`.

Ví dụ nên để root query ở controller riêng:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Không đặt `@SchemaMapping(typeName = "Book")` trên controller chỉ chuyên xử lý root query. Root mapping đã có annotation chuyên biệt và type root riêng; tách controller giúp tránh nhầm phạm vi giữa `Query.book` và `Book.author`.

## 8. Kết hợp class-level mapping với @BatchMapping

Khi một field của `Book` cần được resolve cho nhiều parent object, có thể dùng `@BatchMapping` để gom các yêu cầu tải dữ liệu.

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
```

Trong ví dụ, `@BatchMapping` khai báo rõ cả `typeName` và `field` để thể hiện đầy đủ mapping `Book.author`. Phương thức nhận nhiều source object và trả về kết quả ánh xạ từng `Book` với `Author` tương ứng. Với các method `@SchemaMapping` thông thường trong controller, `typeName` có thể được dùng chung từ annotation cấp class.

Với batch method, cần bảo đảm cách ánh xạ kết quả đúng cho từng source object, kể cả trường hợp không có tác giả. Nếu dùng `Map`, key cần nhất quán với source object; nếu dùng `List`, thứ tự kết quả phải tương ứng với thứ tự input theo hợp đồng của batch loader. Khi cần kiểm soát key, cache hoặc cách tải dữ liệu phức tạp hơn, có thể dùng `BatchLoaderRegistry` và DataLoader.

Class-level `@SchemaMapping` giúp tránh lặp type name trong các mapping cùng controller; nó không tự giải quyết N+1. Việc gom request được thực hiện bởi batch mapping/DataLoader và cần được kiểm chứng bằng số lần gọi repository hoặc service.

## 9. Không tạo mapping trùng

Mỗi cặp GraphQL type và field cần có một cách resolve rõ ràng. Tránh khai báo cùng một field ở nhiều method hoặc vừa đăng ký annotated mapping vừa tự gắn `DataFetcher` cho chính field đó trong custom runtime wiring.

Ví dụ không nên có hai method cùng ánh xạ `Book.author`:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(field = "author")
    public Author loadAuthor(Book book) {
        return anotherService.load(book.authorId());
    }
}
```

Hai method cùng khai báo resolver cho `Book.author`; việc đăng ký có thể gây lỗi hoặc xung đột khi xây dựng runtime. Hãy giữ một mapping duy nhất hoặc thay thế mapping cũ sau khi xác định rõ trách nhiệm.

Nếu class-level type là `Book` nhưng method-level override thành `Magazine`, cần chắc chắn method đó thực sự xử lý field của `Magazine`. Override không nên được dùng để che giấu ranh giới controller không rõ ràng.

## 10. Kiểm thử class-level mapping bằng GraphQlTester

`GraphQlTester` có thể kiểm tra operation đi qua schema và controller mapping. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest({BookQueryController.class, BookController.class})
class BookSchemaMappingTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesBookAuthor() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

Ví dụ giả định test context có mock hoặc test bean cho `BookService` và `AuthorService`, đồng thời các bean trả về dữ liệu khớp ID trong query. Test xác minh root query trả Book và class-level mapping đưa `Book.author` tới đúng handler method.

Nên kiểm thử thêm:

- Hai hoặc nhiều method trong cùng controller cùng dùng type mặc định.
- Method có `field` tường minh khác tên method.
- Method-level `typeName` override khi thực sự cần.
- Argument của nested field và source object được truyền đúng.
- Batch mapping với nhiều source object và trường hợp không có dữ liệu liên quan.
- Không có mapping trùng giữa controller và custom runtime wiring.

Slice test có thể cần khai báo rõ các controller liên quan và cung cấp mock cho dependency của chúng. Với kiểm thử toàn bộ auto-configuration, schema resources và HTTP transport, dùng integration test phù hợp thay vì chỉ dựa vào `@GraphQlTest`.

## 11. Lỗi thường gặp khi dùng class-level @SchemaMapping

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Method không được đăng ký | Method thiếu annotation mapping | Thêm `@SchemaMapping` hoặc annotation handler phù hợp trên method |
| Field được ánh xạ vào sai type | Class-level `typeName` không khớp SDL | Kiểm tra tên GraphQL object type |
| Tên field không khớp | Method name khác field trong SDL | Khai báo `field` tường minh |
| Controller không được phát hiện | Thiếu `@Controller` hoặc ngoài component scan | Kiểm tra Spring bean và package scan |
| Argument nhận null | Tên argument hoặc kiểu binding không đúng | Dùng `@Argument("...")` và kiểm tra SDL |
| Hai method cùng xử lý một field | Mapping bị khai báo trùng | Giữ một handler cho mỗi type/field |
| Field root query không chạy | Dùng nhầm object type mapping cho root operation | Dùng `@QueryMapping` trong controller phù hợp |
| Query vẫn bị N+1 | Class-level mapping chỉ chia sẻ type name | Dùng `@BatchMapping` hoặc DataLoader |

Khi debug, lần theo ba thông tin: GraphQL type chứa field, tên field trong SDL và method Java được đăng ký. Sau đó kiểm tra type mặc định ở class-level, field suy ra từ tên method hay khai báo tường minh, và việc controller có thực sự nằm trong application context hay không.

## 12. Checklist trước khi dùng class-level @SchemaMapping

- Các handler trong controller có cùng GraphQL object type không?
- `@Controller` đã đăng ký class thành Spring bean chưa?
- `typeName` trên class có trùng tên type trong SDL không?
- Mỗi handler method đã có annotation mapping phù hợp chưa?
- Field có thể suy ra từ method name hay cần `field` tường minh?
- Method-level override có thực sự cần thiết và đúng type không?
- Source object và argument được khai báo đúng chưa?
- Root operation có được đặt trong controller dùng `@QueryMapping`, `@MutationMapping` hoặc `@SubscriptionMapping` phù hợp không?
- Có resolver trùng hoặc custom data fetcher xung đột không?
- Các field có nguy cơ N+1 đã cân nhắc batch mapping/DataLoader chưa?
- Test đã xác minh nhiều mapping trong cùng controller chưa?

Class-level `@SchemaMapping` giúp nhóm các resolver theo GraphQL object type và tránh lặp `typeName` ở từng method. Annotation cấp class chỉ cung cấp type mặc định; từng method vẫn cần mapping annotation và field name phải khớp hợp đồng SDL. Khi controller tập trung vào một type, mapping được đặt tên rõ ràng và test bao phủ các field quan trọng, code Spring for GraphQL sẽ dễ đọc, dễ dò lỗi và dễ mở rộng theo schema.
