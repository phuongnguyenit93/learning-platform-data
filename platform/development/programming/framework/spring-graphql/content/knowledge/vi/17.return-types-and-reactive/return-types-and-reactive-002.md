# Optional return type

## 1. Vì sao resolver cần biểu diễn kết quả có thể không tồn tại?

Khi client truy vấn một đối tượng theo ID, có thể hệ thống tìm thấy bản ghi hoặc không tìm thấy. Ví dụ `book(id: "book-42")` có thể trả về một quyển sách, nhưng `book(id: "unknown")` không có đối tượng tương ứng.

Ở Java, `Optional<T>` biểu diễn một kết quả có thể có hoặc không có giá trị mà không cần dùng `null` làm giá trị trả về trực tiếp. Nhiều Spring Data repository đã sử dụng kiểu này cho phương thức tìm một bản ghi, chẳng hạn `findById` trả về `Optional<Book>`.

Trong GraphQL, trạng thái không có dữ liệu được biểu diễn bằng `null` nếu field được khai báo nullable. GraphQL không có kiểu `Optional` trong SDL. Khi resolver trả về `Optional<T>`, GraphQL Java có thể mở wrapper này để lấy giá trị bên trong; `Optional.empty()` trở thành `null`, còn `Optional.of(value)` trở thành chính `value`.

Vì vậy, `Optional<T>` là cách biểu diễn ở Java, còn dấu `!` trong schema mới quyết định GraphQL có chấp nhận kết quả `null` hay không.

## 2. Khai báo field nullable trong SDL

Giả sử API tìm sách theo mã:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    isbn: String!
}
```

Kiểu trả về của `book` là `Book`, không có dấu `!`, nên field có thể trả về `null` khi không tìm thấy sách. Argument `id: ID!` vẫn bắt buộc và không được nhận `null`.

Query:

```graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
        isbn
    }
}
```

Khi có sách, response chứa object `Book`. Khi không có sách, response có thể là:

```json
{
  "data": {
    "book": null
  }
}
```

Đây là một kết quả hợp lệ theo schema. Không tìm thấy bản ghi không nhất thiết là lỗi thực thi GraphQL; nó có thể là kết quả bình thường của một truy vấn tìm kiếm.

## 3. Trả về `Optional<T>` từ `@QueryMapping`

Spring Data repository thường đã trả về `Optional<T>` khi tìm một bản ghi. Có thể giữ kiểu đó xuyên qua service và resolver:

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, String> {
}
```

Service:

```java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Optional<Book> findById(String id) {
        return bookRepository.findById(id);
    }
}
```

Resolver:

```java
import java.util.Optional;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookQueryService bookQueryService;

    public BookQueryController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public Optional<Book> book(@Argument String id) {
        return bookQueryService.findById(id);
    }
}
```

Khi resolver trả về `Optional<Book>`, GraphQL Java dùng cơ chế value unboxing mặc định để lấy giá trị bên trong. Kết quả thực thi tương đương với việc resolver trả về `Book` khi có dữ liệu hoặc `null` khi `Optional` rỗng. Spring for GraphQL đăng ký phương thức controller làm data fetcher; việc unbox `Optional` thuộc cơ chế thực thi của GraphQL Java.

Điều này giúp resolver giữ được hợp đồng rõ ràng với service. Không cần gọi `.get()` và cũng không cần tự chuyển mọi trường hợp thành `null` ngay tại controller.

## 4. `Optional.empty()` và `Optional.of(value)` được xử lý thế nào?

GraphQL Java cung cấp `ValueUnboxer` và implementation mặc định `DefaultValueUnboxer` để xử lý các wrapper như `java.util.Optional`.

| Giá trị Java từ resolver | Giá trị sau khi unbox | Kết quả GraphQL với field nullable |
| --- | --- | --- |
| `Optional.of(book)` | `book` | Object `Book` |
| `Optional.empty()` | `null` | `null` |
| `null` | `null` | `null` |

Ví dụ:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    if ("book-42".equals(id)) {
        return Optional.of(new Book(
            "book-42",
            "Spring for GraphQL",
            "9780000000042"
        ));
    }

    return Optional.empty();
}
```

Với ID `book-42`, client nhận object sách. Với ID khác, client nhận `book: null` nếu SDL khai báo field nullable. Giá trị `Optional.empty()` không tự tạo GraphQL error và không tự đặt HTTP status thành 404.

Không dùng `Optional.of(value)` nếu `value` có thể null. Nếu nguồn dữ liệu có thể trả null, dùng `Optional.ofNullable(value)` hoặc tốt hơn là giữ kết quả `Optional` từ repository.

## 5. Nullability trong SDL vẫn là quy tắc quyết định

`Optional.empty()` được unbox thành `null`. Vì vậy, nếu field được khai báo non-null, kết quả này vi phạm hợp đồng schema.

Ví dụ:

```graphql
type Query {
    book(id: ID!): Book!
}
```

Resolver:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    return bookRepository.findById(id);
}
```

Nếu repository trả `Optional.empty()`, GraphQL nhận giá trị null cho field `Book!`. GraphQL tạo lỗi thực thi về non-null field và đẩy null lên field cha gần nhất có thể nhận null. Vì `book` nằm ngay dưới root `Query`, kết quả `data` có thể trở thành `null`.

Do đó, hãy chọn nullability dựa trên ý nghĩa nghiệp vụ:

- Dùng `Book` khi không tìm thấy là kết quả bình thường và client cần nhận `null`.
- Dùng `Book!` khi hợp đồng bảo đảm luôn có sách hoặc việc không tìm thấy phải được biểu diễn thành lỗi.
- Nếu không tìm thấy là lỗi nghiệp vụ, có thể ném domain exception và ánh xạ thành GraphQL error thay vì trả `Optional.empty()`.

Không dùng `Optional<T>` để né tránh việc thiết kế nullability. Java wrapper và GraphQL schema phải mô tả cùng một chính sách dữ liệu.

## 6. Dùng Optional cho field lồng nhau

Optional cũng hữu ích với field của object type khi quan hệ có thể không tồn tại. Ví dụ một quyển sách có thể chưa được gán nhà xuất bản:

```graphql
type Book {
    id: ID!
    title: String!
    publisher: Publisher
}

type Publisher {
    id: ID!
    name: String!
}
```

Resolver:

```java
@Controller
public class BookFieldController {

    private final PublisherRepository publisherRepository;

    public BookFieldController(PublisherRepository publisherRepository) {
        this.publisherRepository = publisherRepository;
    }

    @SchemaMapping(typeName = "Book", field = "publisher")
    public Optional<Publisher> publisher(Book book) {
        return publisherRepository.findById(book.publisherId());
    }
}
```

Nếu không có publisher tương ứng, field `publisher` trả về `null`; các field khác của `Book` vẫn có thể được trả về bình thường. Nếu SDL khai báo `publisher: Publisher!`, trường hợp thiếu publisher sẽ tạo lỗi non-null như phần trước.

Với field quan hệ được tải cho nhiều parent object, cần cân nhắc `@BatchMapping` hoặc DataLoader để tránh N+1. Việc resolver trả `Optional` chỉ giải quyết cách biểu diễn một kết quả có thể vắng mặt; nó không tự tối ưu số lần gọi repository.

## 7. Optional khác với danh sách rỗng

Không nên nhầm `Optional.empty()` với một collection không có phần tử. Hai kết quả mang ý nghĩa khác nhau:

```graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
```

- `book` tìm một đối tượng: không tìm thấy có thể trả `null` thông qua `Optional.empty()`.
- `booksByAuthor` tìm nhiều đối tượng: không có sách phù hợp nên trả danh sách rỗng `[]`.

Ví dụ Java:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    return bookRepository.findById(id);
}

@QueryMapping
public List<Book> booksByAuthor(@Argument String authorId) {
    return bookRepository.findAllByAuthorId(authorId);
}
```

Với `[Book!]!`, danh sách rỗng là giá trị hợp lệ. Không nên trả `Optional.empty()` để biểu diễn một danh sách không có phần tử, vì nó trở thành `null` và vi phạm non-null của list. Hãy dùng `List.of()` hoặc collection rỗng phù hợp.

`Optional<List<Book>>` chỉ nên được cân nhắc khi domain thực sự phân biệt “không có collection” với “collection tồn tại nhưng rỗng”. Trong phần lớn GraphQL list query, một list rỗng là biểu diễn đơn giản và dễ hiểu hơn.

## 8. Optional và kiểu reactive `Mono<T>`

Spring for GraphQL hỗ trợ các kiểu reactive như `Mono<T>` và `Flux<T>` trong annotated controller. Với một kết quả đơn lẻ có thể không tồn tại, `Mono<T>` có thể phát ra một giá trị hoặc hoàn tất mà không phát giá trị.

Ví dụ:

```java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookReactiveRepository.findById(id);
}
```

Nếu `Mono` phát ra `Book`, field nhận object đó. Nếu `Mono` hoàn tất rỗng, Spring for GraphQL chuyển kết quả reactive thành giá trị hoàn tất null để GraphQL xử lý theo nullability của field. Điều này tương tự ý nghĩa của `Optional.empty()` đối với field nullable.

Không cần bọc một `Mono<Book>` trong `Optional` hoặc dùng `Mono<Optional<Book>>` nếu không có nhu cầu domain đặc biệt. Chọn một kiểu biểu diễn phù hợp với tầng dữ liệu:

| Mô hình xử lý | Kiểu trả về phù hợp |
| --- | --- |
| Repository đồng bộ trả một kết quả có thể thiếu | `Optional<Book>` |
| Resolver đồng bộ trả kết quả có thể thiếu | `Optional<Book>` hoặc `Book` nullable |
| Repository/reactive service trả một kết quả bất đồng bộ | `Mono<Book>` |
| Resolver trả nhiều kết quả reactive | `Flux<Book>` hoặc `Mono<List<Book>>` tùy hợp đồng |

`Mono.empty()` và `Optional.empty()` đều có thể dẫn đến null ở GraphQL, nhưng chúng thuộc hai mô hình xử lý khác nhau. Không chuyển reactive flow sang blocking chỉ để tạo `Optional`.

## 9. Chọn giữa Optional, null và exception

Ba cách biểu diễn thường gặp có ý nghĩa khác nhau:

| Cách trả về | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| `Optional.empty()` | Không có kết quả | Không tìm thấy là kết quả bình thường của field nullable |
| `null` | Không có giá trị | Resolver đơn giản hoặc API cũ đã dùng nullable return |
| Ném exception | Lần thực thi gặp lỗi | Không tìm thấy là lỗi nghiệp vụ hoặc có lỗi hệ thống cần báo client |

Ví dụ tìm kiếm có thể không có kết quả:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    return bookQueryService.findById(id);
}
```

Ví dụ nghiệp vụ yêu cầu sách phải tồn tại:

```java
@QueryMapping
public Book requiredBook(@Argument String id) {
    return bookQueryService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
}
```

`BookNotFoundException` có thể được xử lý bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` để trả lỗi có mã và thông báo phù hợp. Hãy thống nhất giữa SDL và exception handling; không nên vừa khai báo field nullable để biểu diễn “không tìm thấy bình thường” vừa ném exception cho mọi trường hợp thiếu dữ liệu nếu client không cần hành vi đó.

Không dùng `Optional.get()` mà không kiểm tra. Cách gọi đó có thể ném `NoSuchElementException`, biến một kết quả vắng mặt bình thường thành lỗi thực thi ngoài ý muốn.

## 10. Optional trong input không giống Optional trong output

Ở output, `Optional.empty()` được unbox thành null và GraphQL áp dụng nullability của field. Ở input, GraphQL còn phân biệt một argument bị bỏ qua với argument được truyền rõ ràng là `null`.

Điều này quan trọng với Mutation cập nhật một phần. Ví dụ client có thể muốn:

- Không gửi `description`: giữ nguyên mô tả hiện tại.
- Gửi `description: null`: xóa mô tả hiện tại.
- Gửi `description: "New text"`: cập nhật mô tả.

Một tham số `@Argument` thông thường không luôn giữ được sự khác biệt giữa giá trị bị bỏ qua và giá trị null. Spring for GraphQL cung cấp `ArgumentValue<T>` để biểu diễn giá trị cùng cờ cho biết argument có bị omitted hay không.

Ví dụ:

```java
@MutationMapping
public Book updateBook(
        @Argument String id,
        @Argument ArgumentValue<String> description) {

    return bookService.updateDescription(
        id,
        description.isOmitted(),
        description.value()
    );
}
```

`ArgumentValue` phù hợp khi nghiệp vụ cần phân biệt omitted và explicit null. Không dùng `Optional<T>` làm vật thay thế cho cơ chế này nếu cần giữ đủ ba trạng thái.

## 11. Kiểm thử Optional return type bằng `GraphQlTester`

Nên kiểm tra cả trường hợp `Optional.of(value)` và `Optional.empty()` để bảo đảm resolver khớp với nullability của schema.

Schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Kiểm thử trường hợp tìm thấy:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class OptionalBookQueryTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookWhenPresent() {
        graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }

    @Test
    void returnsNullWhenOptionalIsEmpty() {
        graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                }
            }
            """)
            .execute()
            .path("book")
            .valueIsNull();
    }
}
```

Ví dụ giả định repository hoặc fixture trả `Optional.of(book)` cho `book-42` và `Optional.empty()` cho `missing`. Khi test trường hợp không tìm thấy, `GraphQlTester` xác nhận field thực sự là null và response không có lỗi ngoài dự kiến.

Nên bổ sung một test riêng cho schema non-null (`Book!`) để xác nhận `Optional.empty()` tạo GraphQL error và null propagation đúng như hợp đồng. Kiểm thử cả giá trị `Optional.of` lẫn `Optional.empty` giúp phát hiện resolver hoặc schema không đồng bộ.

## 12. Lỗi thường gặp khi dùng Optional

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client nhận null dù repository có dữ liệu | Service tạo `Optional.empty()` sai hoặc truy vấn không đúng khóa | Kiểm tra repository và mapping dữ liệu trước khi trả về |
| Query phát lỗi non-null khi không tìm thấy | SDL khai báo field `Book!` nhưng resolver trả `Optional.empty()` | Đổi field thành nullable nếu absence là bình thường, hoặc ném exception theo nghiệp vụ |
| Resolver ném `NoSuchElementException` | Gọi `Optional.get()` khi không có giá trị | Trả Optional trực tiếp, dùng `orElse`, `orElseGet` hoặc `orElseThrow` có chủ đích |
| List field trả null khi không có phần tử | Dùng `Optional.empty()` để biểu diễn list rỗng | Trả collection rỗng cho field list non-null |
| API trả null và errors không nhất quán | Trộn `Optional.empty()` với exception cho cùng một trường hợp | Xác định rõ absence là kết quả bình thường hay lỗi nghiệp vụ |
| Resolver dùng nhiều lớp wrapper khó hiểu | Kết hợp `Optional`, `Mono`, `CompletableFuture` không cần thiết | Chọn một kiểu phù hợp với mô hình đồng bộ hoặc reactive |
| Mutation không phân biệt omitted và null | Dùng `Optional<T>` cho input partial update | Dùng `ArgumentValue<T>` khi cần phân biệt hai trạng thái |
| Nghĩ Optional làm field GraphQL thành nullable | Không xem xét kiểu trong SDL | Quyết định nullability bằng `T` hoặc `T!` trong schema |

## 13. Checklist thiết kế Optional return type

- [ ] Dùng `Optional<T>` cho kết quả đơn lẻ có thể không tồn tại.
- [ ] SDL khai báo field nullable nếu `Optional.empty()` là kết quả hợp lệ.
- [ ] Hiểu rằng GraphQL Java unbox `Optional.of(value)` thành value và `Optional.empty()` thành null.
- [ ] Không gọi `Optional.get()` mà không kiểm tra.
- [ ] Không dùng Optional rỗng để thay cho list rỗng.
- [ ] Chọn rõ giữa absence bình thường và lỗi nghiệp vụ.
- [ ] Dùng `Mono<T>` khi tầng dữ liệu là reactive thay vì chuyển sang blocking.
- [ ] Không lạm dụng wrapper lồng nhau như `Mono<Optional<T>>`.
- [ ] Dùng `ArgumentValue<T>` cho input cần phân biệt omitted và explicit null.
- [ ] Kiểm thử cả kết quả có giá trị, Optional rỗng và non-null propagation.

## Kết luận

`Optional<T>` là kiểu trả về hữu ích khi resolver cần biểu diễn một đối tượng có thể không tồn tại. Với Spring for GraphQL, phương thức controller có thể trả kiểu giá trị mà GraphQL Java xử lý; `DefaultValueUnboxer` mở `Optional.of(value)` thành value và `Optional.empty()` thành null. SDL vẫn là nơi quyết định field có chấp nhận null hay không.

Hãy dùng field nullable khi không tìm thấy là kết quả bình thường, dùng exception khi đó là lỗi nghiệp vụ và dùng danh sách rỗng cho list query không có phần tử. Với resolver reactive, `Mono<T>` đã biểu diễn một giá trị có thể vắng mặt. Với input partial update, dùng `ArgumentValue<T>` nếu cần phân biệt argument bị bỏ qua với argument được truyền rõ ràng là null.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — ValueUnboxer API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ValueUnboxer.html)
- [GraphQL Specification — Type System and Non-Null](https://spec.graphql.org/October2021/#sec-Non-Null)
