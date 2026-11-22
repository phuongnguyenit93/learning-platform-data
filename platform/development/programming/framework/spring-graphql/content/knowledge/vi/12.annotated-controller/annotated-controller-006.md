# Tên field mặc định từ method

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách Spring for GraphQL suy luận tên field từ tên method trong annotated controller.
- Phân biệt quy tắc suy luận field name và type name.
- Dùng `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` cho các root field.
- Dùng `@SchemaMapping` để ánh xạ field của object type.
- Ghi đè tên field hoặc type bằng thuộc tính annotation khi tên Java khác SDL.
- Nhận biết lỗi mapping do tên method, source parameter hoặc mapping trùng lặp.
- Viết controller có tên method rõ ràng và ổn định với GraphQL schema.

## 1. Vì sao tên method ảnh hưởng đến GraphQL field?

Trong Spring for GraphQL, annotated controller giúp kết nối method Java với field trong GraphQL schema. Bạn không cần tự đăng ký từng `DataFetcher` như khi làm việc trực tiếp với GraphQL Java.

Spring có thể suy luận mapping từ tên method và kiểu tham số source. Nhờ vậy, controller thường ngắn gọn:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Với quy ước mặc định:

- `bookById` được ánh xạ tới field `Query.bookById`.
- `author` được ánh xạ tới field `Book.author`.
- Kiểu tham số source `Book` giúp Spring xác định parent GraphQL type cho `author`.

Quy tắc này giúp tên Java và tên field GraphQL nhất quán. Khi method cần tên khác với field trong SDL, có thể khai báo tên tường minh qua annotation.

## 2. Quy tắc suy luận mặc định

Có hai thông tin chính Spring cần xác định khi đăng ký một field mapping:

1. **Field name:** tên field GraphQL mà method xử lý.
2. **Type name:** GraphQL type sở hữu field đó.

Cách suy luận phụ thuộc vào annotation được dùng:

| Annotation | Type name mặc định | Field name mặc định |
|---|---|---|
| `@QueryMapping` | `Query` | Tên method |
| `@MutationMapping` | `Mutation` | Tên method |
| `@SubscriptionMapping` | `Subscription` | Tên method |
| `@SchemaMapping` | Suy ra từ kiểu source parameter | Tên method |
| `@BatchMapping` | Suy ra từ kiểu source parameter | Tên method |

Các annotation Query, Mutation và Subscription là cách viết chuyên biệt cho root type tương ứng. Với field thuộc object type khác, dùng `@SchemaMapping` hoặc `@BatchMapping`.

### Field name được lấy từ tên method

Ví dụ schema:

~~~graphql
type Query {
  books: [Book!]!
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Spring đăng ký method `books` cho `Query.books` và method `bookById` cho `Query.bookById`. Không cần truyền tên field vào annotation khi tên method đã khớp SDL.

### Type name được suy ra từ source parameter

Với field lồng, tham số source là object cha đang được phân giải. Kiểu Java của tham số này được dùng để suy ra GraphQL type.

Schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Method `author` được ánh xạ tới field `Book.author` vì:

- Tên method là `author`.
- Source parameter có kiểu Java `Book`.
- GraphQL schema có object type `Book` với field `author`.

Tham số `book` là source object được trả về từ field cha, ví dụ `Query.bookById`. Spring đưa object đó vào method khi cần phân giải `Book.author`.

Tên biến `book` không quyết định type name; kiểu Java `Book` mới là thông tin quan trọng. Đổi tên biến thành `source` không làm thay đổi mapping.

## 3. @QueryMapping: tên method trở thành field của Query

`@QueryMapping` là shortcut cho mapping trên root type `Query`. Tên method được dùng làm tên field nếu không khai báo tên khác.

SDL:

~~~graphql
type Query {
  product(id: ID!): Product
  featuredProducts: [Product!]!
}
~~~

Controller:

~~~java
@Controller
public class ProductController {

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }

    @QueryMapping
    public List<Product> featuredProducts() {
        return productService.findFeatured();
    }
}
~~~

Kết quả mapping:

| Method Java | GraphQL field |
|---|---|
| `product(...)` | `Query.product` |
| `featuredProducts()` | `Query.featuredProducts` |

Tên method cần khớp với field trong SDL. Ví dụ, nếu schema dùng `product` nhưng method có tên `findProduct`, Spring sẽ mặc định tìm field `Query.findProduct`. Khi đó cần đổi tên method hoặc khai báo tên field rõ ràng.

## 4. @MutationMapping và @SubscriptionMapping cũng dùng tên method

Quy tắc suy luận tên field tương tự được áp dụng cho Mutation và Subscription.

SDL:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
  deleteBook(id: ID!): Boolean!
}

type Subscription {
  bookAdded: Book!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }

    @MutationMapping
    public boolean deleteBook(@Argument String id) {
        return bookService.delete(id);
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return bookEventPublisher.bookAdded();
    }
}
~~~

Spring suy luận:

- `createBook` → `Mutation.createBook`.
- `deleteBook` → `Mutation.deleteBook`.
- `bookAdded` → `Subscription.bookAdded`.

Return type, argument hoặc tên biến không quyết định tên field. Nếu method được đặt tên theo quy ước nghiệp vụ khác với schema, dùng thuộc tính tên trên annotation để khai báo mapping tường minh.

## 5. @SchemaMapping: tên method và source type xác định field lồng

`@SchemaMapping` dùng để xử lý field của một GraphQL type bất kỳ. Khi không khai báo thuộc tính, Spring suy luận:

- Field name từ tên method.
- Type name từ kiểu source parameter.

Ví dụ schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
}

type Review {
  id: ID!
  rating: Int!
}
~~~

Controller:

~~~java
@Controller
public class BookFieldController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }
}
~~~

Mapping tương ứng:

| Method | Source parameter | GraphQL mapping |
|---|---|---|
| `author(Book book)` | `Book` | `Book.author` |
| `reviews(Book book)` | `Book` | `Book.reviews` |

Một method có thể nhận thêm argument hoặc context parameter. Source object vẫn là tham số được Spring nhận diện là parent object; các tham số được đánh dấu bằng annotation như `@Argument` hoặc `@ContextValue` có mục đích riêng.

Ví dụ:

~~~java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument Integer minRating) {

    return reviewService.findByBookIdAndMinRating(
            book.getId(), minRating);
}
~~~

Method trên vẫn xử lý `Book.reviews`; argument `minRating` chỉ bổ sung điều kiện lọc.

## 6. Ghi đè field name khi method có tên khác

Tên method thường nên khớp tên field, nhưng không phải lúc nào cũng thuận tiện. Có thể method được đặt tên theo ý nghĩa nghiệp vụ hoặc theo quy ước Java trong khi schema dùng tên ngắn hơn.

Với `@QueryMapping`, dùng thuộc tính `name` để chỉ định field:

~~~java
@Controller
public class BookController {

    @QueryMapping(name = "book")
    public Book findBookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Dù method tên `findBookById`, Spring vẫn ánh xạ tới `Query.book`.

Với `@MutationMapping` và `@SubscriptionMapping`, có thể chỉ định tên field theo cùng cách:

~~~java
@MutationMapping(name = "renameBook")
public Book updateBookTitle(
        @Argument String id,
        @Argument String title) {
    return bookService.rename(id, title);
}

@SubscriptionMapping(name = "bookEvents")
public Flux<BookEvent> streamBookChanges() {
    return bookEventPublisher.events();
}
~~~

Với `@SchemaMapping`, dùng thuộc tính `field`:

~~~java
@SchemaMapping(field = "author")
public Author resolveBookAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Method `resolveBookAuthor` vẫn ánh xạ tới field `author`. Type name tiếp tục được suy ra từ source parameter `Book`.

Có thể ghi cả hai thuộc tính để mapping hoàn toàn tường minh:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author resolveBookAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Cách khai báo này hữu ích khi tên class Java khác tên GraphQL type hoặc khi muốn người đọc controller thấy ngay mapping đích.

## 7. Ghi đè type name khi Java class khác GraphQL type

Thông thường, kiểu source Java có thể suy ra type name theo quy ước đặt tên. Nhưng domain model có thể dùng tên khác với schema công khai.

Ví dụ Java dùng class `CatalogEntry`, trong khi GraphQL công bố object type `Book`:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Controller:

~~~java
@Controller
public class CatalogEntryController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(CatalogEntry entry) {
        return authorService.findById(entry.getAuthorId());
    }
}
~~~

Ở đây, `typeName = "Book"` nói rõ field thuộc GraphQL type `Book`, còn tham số `CatalogEntry` là source object Java. Spring không cần suy ra GraphQL type name từ tên class trong trường hợp này.

Hãy dùng cách này khi DTO, projection hoặc domain object có tên khác schema. Không cần đổi tên class Java chỉ để làm nó trùng tên GraphQL type.

## 8. Quy tắc suy luận không phải JavaBean getter mapping

Tên method trong annotated controller được dùng làm field mapping theo quy tắc annotation. Không nên giả định Spring sẽ tự loại bỏ tiền tố `get` hoặc `is` như khi ánh xạ JavaBean property.

Ví dụ, method:

~~~java
@SchemaMapping
public Author getAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Theo quy tắc suy luận từ tên method, field đích mặc định là `Book.getAuthor`. Nếu SDL khai báo field `author`, hãy đổi tên method thành `author` hoặc chỉ định rõ:

~~~java
@SchemaMapping(field = "author")
public Author getAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Tương tự, một method tên `isAvailable` không nên được kỳ vọng tự động map tới field `available`. Hãy đặt tên method trùng field hoặc dùng thuộc tính `field` để tránh nhầm lẫn.

Điều này cũng giúp code review dễ dàng hơn: người đọc có thể xác định mapping từ annotation và tên method mà không phải đoán quy tắc JavaBean.

## 9. @BatchMapping cũng suy luận field từ method

`@BatchMapping` là cách khai báo batch resolver cho một field, thường dùng để tải dữ liệu liên quan cho nhiều source object cùng lúc. Quy tắc tên field mặc định vẫn dựa trên tên method; type name được suy ra từ kiểu source trong collection.

Ví dụ:

~~~graphql
type Book {
  id: ID!
  author: Author
}
~~~

~~~java
@Controller
public class BookBatchController {

    @BatchMapping
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .collectMap(
                        Author::getId,
                        Function.identity()
                )
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();

                    for (Book book : books) {
                        result.put(
                                book,
                                authorsById.get(book.getAuthorId()));
                    }

                    return result;
                });
    }
}
~~~

Spring suy luận method `author` là batch mapping cho field `Book.author`. Nếu method được đặt tên `loadAuthors`, hãy khai báo rõ field đích bằng thuộc tính `field` của `@BatchMapping`.

Batch mapping giúp giảm số lần gọi nguồn dữ liệu khi một query lấy nhiều Book cùng author. Nó không thay đổi ý nghĩa field trong schema và không thay thế việc chọn đúng type name hoặc field name.

Khi trả về Map, cần bảo đảm key có equality ổn định và map đúng từng source object. Nếu trả về Flux theo thứ tự, thứ tự phần tử phải tương ứng với danh sách source đầu vào.

## 10. Nhiều method cùng tên và mapping trùng lặp

Tên method giống nhau trong các controller khác nhau không nhất thiết tạo xung đột nếu chúng thuộc các GraphQL type khác nhau.

Ví dụ:

~~~java
@Controller
public class BookController {

    @SchemaMapping
    public String label(Book book) {
        return book.getTitle();
    }
}

@Controller
public class AuthorController {

    @SchemaMapping
    public String label(Author author) {
        return author.getName();
    }
}
~~~

Hai method tương ứng với:

- `Book.label`.
- `Author.label`.

Chúng không xung đột vì type name khác nhau.

Ngược lại, nếu hai method cùng được đăng ký cho `Book.label`, Spring không thể chọn tùy ý một method. Mapping trùng lặp hoặc mơ hồ có thể khiến quá trình khởi tạo controller mapping thất bại. Hãy kiểm tra:

- Hai method có cùng type name và field name hay không.
- Một method có đang khai báo tường minh field đã được method khác sở hữu không.
- Có đồng thời đăng ký `@SchemaMapping` và DataFetcher thủ công cho cùng field hay không.
- Có controller được component scan nhiều lần hoặc cấu hình trùng hay không.

Giữ một nơi chịu trách nhiệm chính cho mỗi field mapping giúp tránh lỗi khó chẩn đoán.

## 11. Lỗi thường gặp khi suy luận tên field

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query báo không có field tương ứng | Method name khác field trong SDL | Đổi tên method hoặc dùng `@QueryMapping(name = "...")` |
| Field lồng không được resolve | Source parameter suy ra sai type name | Dùng `@SchemaMapping(typeName = "...")` |
| `getAuthor` không map tới `author` | Tên method được dùng làm field name | Dùng method `author` hoặc `field = "author"` |
| Mutation không tìm thấy field | Method name khác field trong Mutation | Dùng `@MutationMapping(name = "...")` |
| Subscription mapping sai | Method name khác field trong Subscription | Dùng `@SubscriptionMapping(name = "...")` |
| Mapping bị mơ hồ | Có nhiều method đăng ký cùng type và field | Loại bỏ mapping trùng hoặc đổi mapping đích |
| Source parameter không được nhận diện đúng | Method signature có nhiều tham số không rõ vai trò | Kiểm tra annotation của từng parameter và khai báo typeName tường minh |

Khi một field không hoạt động, hãy đối chiếu theo thứ tự:

1. Tên field trong SDL.
2. Tên method Java.
3. Annotation đang dùng và thuộc tính name/field.
4. Type name suy ra từ source parameter.
5. Các mapping khác có cùng type và field.
6. Log khởi tạo annotated controller để tìm lỗi đăng ký mapping.

## 12. Kiểm thử mapping theo tên method

Nên có integration test để xác nhận Spring thực sự ánh xạ method tới field như mong đợi. `GraphQlTester` cho phép thực thi operation trên schema và controller đã cấu hình.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping(name = "book")
    public Book findBook(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(field = "author")
    public Author resolveAuthor(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Test:

~~~java
@Test
void shouldResolveFieldsUsingExplicitNames() {
    graphQlTester.document("""
            query {
                book(id: "b-01") {
                    id
                    title
                    author {
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
~~~

Các trường hợp nên kiểm thử:

- Method name trùng field name và không cần thuộc tính override.
- Method name khác field name nhưng mapping tường minh hoạt động.
- Source Java type được suy ra đúng GraphQL type.
- `typeName` tường minh hoạt động khi Java class có tên khác schema.
- Query, Mutation và Subscription được đăng ký đúng root type.
- Hai controller dùng cùng method name nhưng khác GraphQL type.
- Mapping trùng lặp được phát hiện thay vì âm thầm gọi nhầm method.

## 13. Nguyên tắc đặt tên method trong annotated controller

Để controller dễ đọc và ít phụ thuộc vào cấu hình tường minh:

- Đặt tên method trùng với field GraphQL khi có thể.
- Dùng `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` cho root operation.
- Dùng `@SchemaMapping` cho field của object type.
- Để source parameter thể hiện rõ parent object.
- Chỉ dùng `name`, `field` hoặc `typeName` khi cần tách tên Java khỏi tên schema.
- Không giả định tiền tố `get` hoặc `is` được tự động loại bỏ.
- Tránh đăng ký nhiều method cho cùng một type và field.
- Kiểm thử operation thực tế khi đổi tên method hoặc schema.

Tên method là một phần của quy ước mapping, vì vậy việc đổi tên method có thể làm thay đổi GraphQL field mà Spring đăng ký nếu không có thuộc tính override. Khi refactor, hãy kiểm tra cả controller lẫn SDL và integration test liên quan.

## Kết luận

Spring for GraphQL mặc định dùng tên method để suy luận tên field. Với `@QueryMapping`, `@MutationMapping` và `@SubscriptionMapping`, type name lần lượt là Query, Mutation và Subscription. Với `@SchemaMapping` và `@BatchMapping`, type name được suy ra từ source parameter.

Khi tên method hoặc Java type khác với schema, có thể khai báo `name`, `field` và `typeName` để mapping tường minh. Hiểu đúng quy tắc này giúp controller gọn, dễ đọc, tránh lỗi không tìm thấy field và hạn chế mapping trùng lặp khi ứng dụng phát triển.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Spring for GraphQL — QueryMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/QueryMapping.html)
- [Spring for GraphQL — BatchMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
