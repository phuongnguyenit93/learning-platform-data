# `equals` và `hashCode` của source key trong Spring for GraphQL

Với `@BatchMapping`, Spring for GraphQL gom nhiều parent source thành một batch. Nếu phương thức batch trả về `Map<S, T>`, mỗi key trong map là một source object và value tương ứng là kết quả của field được phân giải cho source đó. Vì `Map` của Java tra cứu key dựa trên `equals()` và `hashCode()`, hai phương thức này quyết định Spring có ghép đúng kết quả với parent source hay không.

Điều này thường ít được chú ý khi dùng Java record hoặc khi map giữ đúng object instance ban đầu. Nhưng nếu batch loader tạo object mới, dùng JPA entity/proxy hoặc source có trạng thái mutable, hai object đại diện cùng một bản ghi có thể không được xem là bằng nhau. Khi đó field có thể nhận `null` dù batch loader đã tải được dữ liệu.

## 1. Source key trong `@BatchMapping` là gì?

Giả sử schema có một danh sách sách và field `Book.author`:

```graphql
type Query {
    books: [Book!]!
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
```

Khi client truy vấn:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

Resolver `Query.books` trả về nhiều `Book`. Thay vì gọi service lấy tác giả riêng cho từng sách, `@BatchMapping` nhận cả danh sách source và tải các tác giả theo lô:

```java
@BatchMapping(typeName = "Book", field = "author")
Mono<Map<Book, Author>> authors(List<Book> books) {
    // Tải tác giả theo authorId của toàn bộ sách.
}
```

Với kiểu trả về `Map<Book, Author>`:

- Key `Book` xác định parent source mà kết quả thuộc về.
- Value `Author` là giá trị cho field `Book.author` của source đó.
- Khi GraphQL hoàn tất field cho từng source, kết quả được ghép theo key tương ứng.

Ví dụ map kết quả:

```java
Map<Book, Author> result = new HashMap<>();
result.put(bookA, authorA);
result.put(bookB, authorB);
```

Spring cần tìm đúng value ứng với source đang được phân giải. Việc tìm key trong `HashMap` tuân theo hợp đồng `equals()` và `hashCode()` của Java.

## 2. Vì sao `equals()` và `hashCode()` quan trọng?

`HashMap` không so sánh mọi key bằng cách nhìn vào các field nghiệp vụ. Nó sử dụng `hashCode()` để xác định bucket, sau đó dùng `equals()` để xác định key có tương đương hay không.

Hợp đồng cơ bản của Java:

1. Nếu `a.equals(b)` là `true`, thì `a.hashCode()` và `b.hashCode()` phải bằng nhau.
2. Hai object có cùng `hashCode()` chưa chắc đã bằng nhau; hash collision là điều được phép.
3. `equals()` cần có tính phản xạ, đối xứng, bắc cầu và nhất quán.
4. Trong thời gian object đang được dùng làm key trong hash-based map, những dữ liệu tham gia vào `equals()` và `hashCode()` cần ổn định.

Ví dụ:

```java
BookSource sourceA = new BookSource(10L, 100L);
BookSource sourceB = new BookSource(10L, 100L);

Map<BookSource, Author> authors = new HashMap<>();
authors.put(sourceA, new Author(100L, "An Nguyen"));

Author result = authors.get(sourceB);
```

Nếu `BookSource` cài đặt equality theo dữ liệu tương ứng, `result` có thể là tác giả đã lưu dù `sourceA` và `sourceB` là hai object instance khác nhau. Nếu class chỉ dùng `Object.equals()` mặc định, hai instance khác nhau không bằng nhau và `result` là `null`.

## 3. Identity equality và value equality

Mặc định, một class Java không override `equals()` và `hashCode()` sẽ dùng hành vi từ `Object`:

- `equals()` chỉ trả `true` khi hai biến tham chiếu tới cùng một object instance.
- `hashCode()` gắn với identity của object trong suốt vòng đời phù hợp của instance.

Đây là **identity equality**. Hai object khác instance dù cùng biểu diễn một bản ghi database vẫn không bằng nhau.

**Value equality** xem hai object là bằng nhau nếu các giá trị được chọn để định danh chúng bằng nhau. Java record tự sinh `equals()` và `hashCode()` dựa trên các component của record:

```java
public record BookSource(Long id, Long authorId) {}

BookSource first = new BookSource(1L, 10L);
BookSource second = new BookSource(1L, 10L);

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Hai record khác instance nhưng có cùng component sẽ bằng nhau. Điều này hữu ích khi batch loader tạo một object source tương đương thay vì dùng đúng instance ban đầu.

Tuy nhiên, record chỉ đúng nếu các component của nó phù hợp để xác định equality. Nếu field thay đổi thường xuyên hoặc chứa association phức tạp, equality tự sinh có thể không phù hợp làm source key. Chọn key theo identity nghiệp vụ ổn định, không chỉ dựa vào việc class có phải record hay không.

## 4. Ví dụ `@BatchMapping` dùng source làm key

Giả sử model là immutable record:

```java
public record Book(Long id, String title, Long authorId) {}

public record Author(Long id, String name) {}
```

Service tải tác giả theo tập ID:

```java
@Service
class AuthorService {

    private final AuthorRepository authorRepository;

    AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    Flux<Author> findAllByIds(Set<Long> ids) {
        return authorRepository.findAllById(ids);
    }
}
```

Batch mapping:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    Mono<Map<Book, Author>> authors(List<Book> books) {
        Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
            .map(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    Author author = authorsById.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
    }
}
```

Ở đây map dùng chính các object `Book` nhận từ danh sách source làm key. Java record đã cài đặt `equals()` và `hashCode()` nên map có thể tra cứu theo value equality nếu framework hoặc batch loader dùng một instance khác có cùng component.

Nếu không tìm thấy tác giả, ví dụ trên bỏ key tương ứng khỏi map. Điều đó dẫn đến field `author` không có kết quả và được xử lý như `null`. Schema khai báo `author: Author` là nullable nên trường hợp này hợp lệ. Nếu schema là `author: Author!`, thiếu value sẽ vi phạm Non-null và có thể kích hoạt null propagation.

## 5. Lỗi khi source class không override equality

Xét class thông thường:

```java
public class BookSource {

    private final Long id;
    private final Long authorId;

    public BookSource(Long id, Long authorId) {
        this.id = id;
        this.authorId = authorId;
    }

    public Long id() {
        return id;
    }

    public Long authorId() {
        return authorId;
    }
}
```

Class này không override `equals()` và `hashCode()`. Hai instance sau đại diện cùng một dữ liệu nhưng không bằng nhau:

```java
BookSource sourceFromQuery = new BookSource(1L, 10L);
BookSource sourceFromBatch = new BookSource(1L, 10L);

Map<BookSource, Author> result = new HashMap<>();
result.put(sourceFromBatch, new Author(10L, "An Nguyen"));

Author author = result.get(sourceFromQuery); // null
```

`HashMap` tìm bằng `sourceFromQuery`, nhưng key được lưu là `sourceFromBatch`. Vì hai object không cùng identity và class không có value equality, map không tìm thấy entry.

Điều này có thể xảy ra khi code tạo một object mới để làm key thay vì dùng chính source nhận được. Hãy kiểm tra nơi tạo key trong batch method, không chỉ kiểm tra dữ liệu bên trong object có giống nhau hay không.

Nếu map luôn dùng đúng các source instance nhận từ tham số `List<S>`, identity equality có thể đủ cho chính map đó. Nhưng không nên phụ thuộc ngầm vào chi tiết này nếu code có thể sao chép, tái tạo hoặc chuyển đổi source object trong các bước tiếp theo.

## 6. Cài đặt equality theo identity nghiệp vụ

Với DTO class thông thường, có thể cài đặt equality dựa trên một định danh ổn định. Ví dụ `BookSource` là DTO immutable, trong đó `id` xác định một source:

```java
public final class BookSource {

    private final Long id;
    private final Long authorId;

    public BookSource(Long id, Long authorId) {
        this.id = id;
        this.authorId = authorId;
    }

    public Long id() {
        return id;
    }

    public Long authorId() {
        return authorId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof BookSource that)) {
            return false;
        }
        return Objects.equals(id, that.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }
}
```

Trong ví dụ này, hai source có cùng `id` được coi là cùng một thực thể logic. `authorId` không tham gia equality vì nó là dữ liệu liên quan chứ không phải định danh của source.

Chỉ chọn `id` làm equality khi ID thực sự ổn định và duy nhất trong phạm vi ứng dụng. Nếu source là transient object chưa có ID, nhiều object có `id == null` có thể bị xem là bằng nhau ngoài ý muốn. Hãy quyết định rõ cách xử lý entity chưa được persist, hoặc dùng DTO có key ổn định khác.

## 7. Các lỗi equality thường gặp với JPA entity

JPA entity thường là class mutable, có lifecycle và có thể được Hibernate bọc bằng proxy. Vì vậy, không nên áp dụng một mẫu `equals()`/`hashCode()` chung cho mọi entity.

### Dùng toàn bộ field trong `equals()` và `hashCode()`

Một số công cụ sinh code có thể tạo equality dựa trên tất cả field. Với entity, điều này dễ gây vấn đề:

- Field mutable thay đổi sau khi entity được đưa vào `HashMap`.
- Association lazy có thể bị tải ngoài ý muốn chỉ để so sánh equality.
- Quan hệ hai chiều có thể tạo vòng lặp khi so sánh hoặc tính hash.
- Hai entity cùng ID nhưng khác trạng thái field có thể bị xem là khác nhau.

Vì vậy, tránh dùng `@Data` của Lombok một cách mặc định trên JPA entity có association. Nếu cần Lombok, cấu hình rõ những field nào tham gia `equals()` và `hashCode()`, hoặc tự cài đặt theo quy tắc entity của dự án.

### Dùng generated ID một cách thiếu cẩn trọng

Nếu ID chỉ được sinh khi persist, hai entity mới có `id == null`. Một implementation chỉ so sánh ID có thể coi mọi entity chưa lưu là bằng nhau. Hash code cũng có thể thay đổi khi ID được gán sau khi object đã được dùng làm key trong map.

Đối với JPA entity, hãy chọn chiến lược equality đã được kiểm chứng cho ORM đang dùng, có xét đến entity transient, persistent và proxy. Một số dự án dùng immutable natural key duy nhất; dự án khác dùng persistent ID với cách xử lý riêng cho transient instance.

### Không tính đến proxy

Hibernate proxy có thể là subclass hoặc wrapper của entity. Kiểm tra `getClass()` trực tiếp trong `equals()` có thể làm entity thật và proxy của cùng entity không được coi là bằng nhau. Cách xử lý class/proxy phụ thuộc ORM và phiên bản; hãy dùng quy ước entity equality của dự án thay vì tự viết một implementation ngắn mà không kiểm tra proxy.

Với GraphQL, một lựa chọn đơn giản thường là chuyển entity sang immutable DTO/record trước khi đưa ra schema. DTO có thể có equality rõ ràng, không kích hoạt lazy loading và không làm lộ lifecycle của persistence layer.

## 8. Không để key thay đổi sau khi đưa vào Map

Một key dùng trong `HashMap` phải giữ ổn định những field tham gia `equals()` và `hashCode()` trong thời gian nằm trong map.

Ví dụ không an toàn:

```java
class MutableBookKey {
    private Long id;

    // equals() và hashCode() đều dựa trên id
}

MutableBookKey key = new MutableBookKey();
Map<MutableBookKey, Author> map = new HashMap<>();
map.put(key, author);

key.setId(10L); // hashCode có thể thay đổi sau khi insert

Author found = map.get(key); // có thể không tìm thấy entry
```

Khi hash code thay đổi, entry vẫn nằm ở bucket cũ nhưng lần tra cứu tính bucket mới. Kết quả là `get(key)` có thể trả về `null` dù map vẫn chứa entry.

Với source key của `@BatchMapping`, nên ưu tiên object immutable hoặc equality dựa trên định danh bất biến. Không sửa field tham gia equality sau khi source đã được dùng làm key.

## 9. Source equality phải phản ánh đúng ý nghĩa field

Không phải cứ hai object có cùng ID là luôn có thể dùng thay thế nhau cho mọi field. Equality cần phù hợp với ý nghĩa của source trong schema.

Ví dụ, nếu `Book.author` chỉ phụ thuộc vào `bookId` thì equality theo `id` có thể hợp lý. Nhưng nếu kết quả của field còn phụ thuộc vào phiên bản, tenant, locale hoặc trạng thái của source, equality chỉ theo ID có thể gộp hai source khác ngữ cảnh thành một key.

DataLoader cũng có thể dùng equality của key để cache và gộp các lần `load()`. Nếu hai source được xem là bằng nhau nhưng thực tế cần kết quả khác nhau, một kết quả có thể bị dùng cho cả hai.

Khi một source có nhiều chiều định danh, cân nhắc:

- Dùng DTO source có equality phản ánh đúng ngữ cảnh cần thiết.
- Dùng key bất biến gồm nhiều thành phần nếu các thành phần đó quyết định kết quả.
- Chuyển sang DataLoader method argument với key rõ ràng như `DataLoader<BookKey, Author>` hoặc `DataLoader<Long, Author>` nếu muốn tách source object khỏi khóa tải dữ liệu.

Không nên đưa mọi field vào `equals()` chỉ để tránh trùng key. Hãy xác định chính xác khi nào hai source có thể dùng chung kết quả của field đang batch.

## 10. Lựa chọn khác: trả về List theo đúng thứ tự source

Với `@BatchMapping`, có thể dùng cách trả về danh sách kết quả theo đúng thứ tự của danh sách source thay vì `Map<S, T>`:

```java
@BatchMapping(typeName = "Book", field = "author")
Mono<List<Author>> authors(List<Book> books) {
    List<Long> authorIds = books.stream()
        .map(Book::authorId)
        .toList();

    return authorService.findAuthorsInOrder(authorIds)
        .collectList();
}
```

Với dạng positional list, phần tử kết quả thứ nhất phải tương ứng với source thứ nhất, phần tử thứ hai với source thứ hai, v.v. Số lượng và thứ tự phải được giữ đúng theo hợp đồng của batch mapping. Cách này tránh yêu cầu source object phải làm key trong `Map`, nhưng service phải bảo đảm thứ tự và cách biểu diễn phần tử không tìm thấy.

Nếu một số quan hệ có thể thiếu, hãy dùng giá trị `null` ở đúng vị trí chỉ khi field GraphQL nullable và kiểu collection được dùng cho phép biểu diễn phần tử đó. Nếu không thể bảo đảm thứ tự, dạng `Map<S, T>` thường dễ kiểm soát hơn, miễn source equality được thiết kế đúng.

## 11. Khi nào nên dùng DataLoader với ID thay cho source key?

Nếu không muốn phụ thuộc vào equality của entity/source object, có thể dùng DataLoader method argument với key là ID hoặc một key value object bất biến.

Đăng ký loader theo ID:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) ->
        authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
    );
```

Resolver:

```java
@SchemaMapping(typeName = "Book", field = "author")
CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
```

Ở đây key của DataLoader là `Long`, không phải `Book`. Equality của key tải dữ liệu là equality của `Long`, vốn đã ổn định. Source vẫn được dùng để lấy `authorId`, nhưng không cần dùng chính source object làm key của kết quả map.

Đổi lại, cách này cần khai báo `BatchLoaderRegistry` và method argument DataLoader rõ ràng. Với source DTO đã có equality tốt, `@BatchMapping` trả `Map<S,T>` thường ngắn gọn hơn.

## 12. Kiểm thử `equals()` và `hashCode()`

Trước khi kiểm thử toàn bộ GraphQL query, nên kiểm tra equality của source type bằng unit test:

```java
class BookSourceEqualityTests {

    @Test
    void equalSourcesHaveSameHashCode() {
        BookSource first = new BookSource(1L, 10L);
        BookSource second = new BookSource(1L, 10L);

        assertThat(first).isEqualTo(second);
        assertThat(first.hashCode()).isEqualTo(second.hashCode());
    }

    @Test
    void mapCanFindEntryByEquivalentSource() {
        BookSource sourceFromQuery = new BookSource(1L, 10L);
        BookSource sourceFromBatch = new BookSource(1L, 10L);
        Author author = new Author(10L, "An Nguyen");

        Map<BookSource, Author> result = new HashMap<>();
        result.put(sourceFromBatch, author);

        assertThat(result.get(sourceFromQuery)).isEqualTo(author);
    }
}
```

Unit test này chứng minh hai instance tương đương có thể dùng thay thế nhau làm map key. Với JPA entity, cần thêm test cho transient entity, entity đã persist, proxy và trạng thái sau khi ID được gán theo đúng chiến lược equality của dự án.

## 13. Kiểm thử tích hợp `@BatchMapping`

Ngoài unit test equality, cần kiểm tra GraphQL response để bảo đảm mỗi source nhận đúng kết quả batch:

```java
@GraphQlTest(BookController.class)
class BookBatchMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void mapsAuthorsToTheirBookSources() {
        given(bookService.findAll()).willReturn(List.of(
            new Book(1L, "Book A", 10L),
            new Book(2L, "Book B", 20L)
        ));

        given(authorService.findAllByIds(Set.of(10L, 20L)))
            .willReturn(Flux.just(
                new Author(10L, "Author A"),
                new Author(20L, "Author B")
            ));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    books {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute();

        response.path("books[0].author.name")
            .entity(String.class).isEqualTo("Author A");
        response.path("books[1].author.name")
            .entity(String.class).isEqualTo("Author B");
    }
}
```

Đây là ví dụ minh họa; các import, static import `given`, model, service và SDL cần có trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Nên bổ sung test với source được tái tạo thành instance khác nhưng có cùng định danh để xác minh equality thực sự cần thiết trong cách xây dựng map của ứng dụng.

## 14. Lỗi thường gặp

**Cho rằng cùng ID đồng nghĩa với cùng object.** Nếu class dùng equality mặc định của `Object`, hai instance khác nhau không bằng nhau dù có cùng ID. Hãy kiểm tra `equals()` và `hashCode()`.

**Override `equals()` nhưng quên `hashCode()`.** Hai object bằng nhau có thể có hash khác nhau, khiến `HashMap` không tìm thấy key. Luôn triển khai cả hai theo cùng định danh.

**Dùng field mutable trong equality.** Thay đổi field sau khi insert có thể làm hash code thay đổi và entry không còn tra cứu được. Ưu tiên key bất biến.

**Dùng toàn bộ association của JPA entity.** Equality có thể kích hoạt lazy loading, tạo vòng lặp hoặc làm hiệu năng giảm. Chọn định danh ổn định và kiểm tra proxy.

**Dùng generated ID khi entity còn transient mà không xử lý `null`.** Nhiều entity chưa có ID có thể bị coi là bằng nhau. Thiết kế riêng cho trạng thái chưa persist.

**Dùng equality quá rộng.** Hai source khác ngữ cảnh nhưng cùng ID có thể bị gộp key, khiến một kết quả được dùng sai cho source khác. Equality phải phản ánh đúng ý nghĩa của field được batch.

**Trả map thiếu key cho field Non-null.** Nếu không có value, field có thể trở thành `null` và vi phạm schema. Chọn nullability hoặc cách biểu diễn lỗi phù hợp.

**Trả List nhưng không giữ thứ tự.** Nếu dùng positional result, mỗi phần tử phải khớp source cùng vị trí. Không thể sắp xếp tùy ý theo thứ tự database trả về.

## Kết luận

Khi `@BatchMapping` trả về `Map<S, T>`, source object là key để ghép kết quả với từng parent. `HashMap` và nhiều map implementation khác dựa vào `hashCode()` rồi `equals()` để tìm key. Hãy dùng source DTO/record immutable có equality phản ánh đúng identity nghiệp vụ, tránh key mutable và cẩn trọng với JPA entity/proxy. Nếu không muốn source object làm key, cân nhắc positional `List` có thứ tự chính xác hoặc DataLoader với ID/key value object rõ ràng. Kiểm thử cả equality độc lập và GraphQL response để phát hiện lỗi ghép source sớm.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: `@BatchMapping`](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Java Platform — `Object.equals` and `Object.hashCode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html)
- [Java Platform — `Map`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html)
