# Batch mapping field name

Trong Spring for GraphQL, **@BatchMapping** ánh xạ một method Java vào một field của GraphQL object type và xử lý field đó cho nhiều source object trong một batch. Tên field có thể được suy ra trực tiếp từ tên method. Khi tên method không trùng với tên field trong SDL, cần chỉ định rõ thuộc tính `field` để Spring đăng ký đúng mapping.

Quy tắc đặt tên này ảnh hưởng trực tiếp đến việc resolver có được gọi hay không. Bài học trình bày cách Spring xác định field và type, khi nào cần khai báo tường minh, cách chọn kiểu trả về Map hoặc List, những lỗi naming mismatch thường gặp và cách kiểm thử.

## 1. @BatchMapping ánh xạ vào field nào?

Giả sử schema có Book và Author:

~~~graphql
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
~~~

Mỗi Book có thể cần tải Author. Nếu dùng `@SchemaMapping`, resolver thường xử lý từng Book một. Với `@BatchMapping`, method nhận danh sách Book và tải Author cho cả nhóm:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findForBooks(books);
    }
}
~~~

Trong ví dụ này, Spring suy ra:

- GraphQL type nguồn là `Book` từ phần tử của `List<Book>`.
- Tên field là `author` từ tên method.
- Method xử lý field `Book.author`.

Tên method `author` khớp với field `author` trong SDL, vì vậy không cần ghi `typeName` và `field` trong annotation.

`@BatchMapping` không tự tạo field mới trong schema. Field vẫn phải được khai báo trong SDL, và tên mapping phải khớp với hợp đồng đó.

## 2. Quy tắc mặc định: tên method là tên field

Khi không chỉ định thuộc tính `field`, Spring dùng tên method làm tên GraphQL field cần ánh xạ.

Ví dụ SDL:

~~~graphql
type Book {
    reviews: [Review!]!
}
~~~

Method:

~~~java
@BatchMapping
public Map<Book, List<Review>> reviews(List<Book> books) {
    return reviewService.findForBooks(books);
}
~~~

Tên method `reviews` được dùng làm tên field. Spring ánh xạ method tới `Book.reviews`.

Tên field được so khớp theo đúng tên GraphQL, bao gồm chữ hoa và chữ thường. GraphQL phân biệt hoa thường, do đó `reviews`, `Reviews` và `review` là những tên khác nhau.

Không có quy tắc tự động đổi tên số nhiều thành số ít hoặc ngược lại. Nếu method tên `authors` thì Spring tìm field `authors`; nó không tự suy luận rằng method đang muốn xử lý field `author`.

Ví dụ sau không ánh xạ vào `Book.author`:

~~~java
@BatchMapping
public Map<Book, Author> authors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Nếu schema chỉ có `Book.author`, cần đổi tên method thành `author` hoặc khai báo `field = "author"`.

## 3. Chỉ định field bằng thuộc tính field

Khi tên method được chọn theo ý nghĩa Java hoặc tên service, có thể chỉ định field GraphQL bằng thuộc tính `field`.

SDL:

~~~graphql
type Book {
    author: Author
}
~~~

Method Java:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Ở đây:

- Tên method Java là `loadAuthors`.
- Tên field GraphQL là `author`.
- `field = "author"` xác định rõ mapping cần đăng ký.

Có thể bỏ `typeName` nếu Spring suy ra được type nguồn từ `List<Book>`. Tuy nhiên, khai báo cả hai thuộc tính giúp người đọc nhìn thấy đầy đủ tọa độ mapping:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Cách viết tường minh hữu ích khi method có tên khác field, khi type Java và tên GraphQL không giống nhau, hoặc khi code có nhiều mapping cần rà soát.

## 4. Quy tắc xác định typeName

Ngoài tên field, Spring cần biết field thuộc GraphQL object type nào. `@BatchMapping` có thể suy ra type từ kiểu source object trong tham số danh sách.

Ví dụ:

~~~java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Spring suy ra source type là Book và field là author.

Nếu muốn chỉ định rõ type GraphQL, dùng `typeName`:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

`typeName` phải là tên object type trong schema SDL, không nhất thiết là tên class Java nếu hai tên đã được ánh xạ khác nhau.

Ví dụ SDL:

~~~graphql
type CatalogBook {
    id: ID!
    writer: Author
}
~~~

Java model vẫn có thể tên Book:

~~~java
public record Book(Long id, Long authorId) {
}
~~~

Khi đó mapping cần chỉ định đúng tên type và field của GraphQL:

~~~java
@BatchMapping(typeName = "CatalogBook", field = "writer")
public Map<Book, Author> loadWriters(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Không dùng `typeName = "Book"` chỉ vì class Java có tên Book nếu SDL thực tế công bố type là CatalogBook.

## 5. Khi nào nên khai báo cả typeName và field?

Có thể dựa vào quy tắc suy luận mặc định khi method và model đơn giản. Tuy nhiên, mapping tường minh thường dễ bảo trì hơn trong các trường hợp sau:

- Method name khác field name.
- GraphQL type name khác tên class Java.
- Source parameter dùng generic hoặc abstraction khiến việc suy luận type khó đọc.
- Có nhiều object type với field trùng tên.
- Muốn reviewer nhận ra ngay tọa độ GraphQL mà method xử lý.

Ví dụ hai type đều có field `owner`:

~~~graphql
type Book {
    owner: User
}

type Article {
    owner: User
}
~~~

Có thể tách hai batch mapping:

~~~java
@BatchMapping(typeName = "Book", field = "owner")
public Map<Book, User> bookOwners(List<Book> books) {
    return userService.findOwnersOfBooks(books);
}

@BatchMapping(typeName = "Article", field = "owner")
public Map<Article, User> articleOwners(List<Article> articles) {
    return userService.findOwnersOfArticles(articles);
}
~~~

Tên method Java có thể khác nhau, nhưng hai tọa độ GraphQL vẫn rõ ràng: `Book.owner` và `Article.owner`.

## 6. Chữ ký method và source object

Một batch mapping nhận một nhóm source object thuộc cùng một GraphQL type. Tham số danh sách thể hiện các object mà field cần được phân giải.

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

`List<Book>` là danh sách source object. Mỗi phần tử tương ứng với một lần phân giải field `Book.author`.

Method không nhận một Book đơn lẻ như `@SchemaMapping` thông thường. Nếu khai báo tham số nguồn không phù hợp, Spring có thể không suy ra được type hoặc không đăng ký được batch mapping như mong đợi.

Một số dạng source parameter có thể làm việc suy luận kém rõ ràng, chẳng hạn raw `List` không có generic type:

~~~java
@BatchMapping
public Map<?, ?> author(List<?> books) {
    // Thiếu kiểu phần tử để suy luận source type.
    return Map.of();
}
~~~

Nên khai báo generic cụ thể:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Dù đã ghi `typeName`, kiểu phần tử cụ thể vẫn giúp chữ ký method rõ ràng và an toàn hơn khi biên dịch.

## 7. Chọn kiểu trả về Map hoặc List

`@BatchMapping` có thể trả kết quả theo hai cách phổ biến:

- `Map<S, V>`: ánh xạ source object sang giá trị field tương ứng.
- `List<V>`: trả danh sách kết quả theo đúng thứ tự của danh sách source object đầu vào.

### Trả về Map

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Map phải dùng chính source object làm key, không phải `authorId`, trừ khi source object thực tế là ID đó. Spring dùng từng Book làm key để tìm Author tương ứng.

Ví dụ:

~~~java
Map<Book, Author> result = new HashMap<>();
result.put(bookA, authorA);
result.put(bookB, authorB);
result.put(bookC, authorC);
return result;
~~~

Không trả `Map<Long, Author>` với key là Book ID nếu method được khai báo `Map<Book, Author>`. Kiểu key phải tương ứng với source object mà Spring dùng để ghép kết quả.

### Trả về List

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    return authorService.findAuthorsInBookOrder(books);
}
~~~

Với kiểu List, phần tử ở vị trí `i` phải là kết quả cho source object ở vị trí `i` trong danh sách đầu vào.

Nếu Spring chuyển vào `[bookA, bookB, bookC]`, kết quả phải tương ứng `[authorA, authorB, authorC]`. Không được trả list theo thứ tự tùy ý từ database.

Nếu một Book không có Author và field nullable, list cần giữ đúng vị trí với giá trị null tương ứng. Vì `List.of()` không cho phép phần tử null, có thể dùng một list mutable hoặc một collection phù hợp.

### Nên chọn cách nào?

| Kiểu trả về | Khi phù hợp | Điều cần bảo đảm |
| --- | --- | --- |
| `Map<Book, Author>` | Có thể lập chỉ mục kết quả theo source object. | Key là đúng Book trong batch đầu vào. |
| `List<Author>` | Service dễ trả kết quả theo đúng thứ tự source. | Thứ tự và số lượng phần tử phải tương ứng. |

Dạng Map thường dễ đọc khi truy vấn repository trả kết quả không theo thứ tự. Dạng List phù hợp nếu service đã có chiến lược sắp xếp chính xác theo danh sách source.

## 8. Trả về kết quả bất đồng bộ

Batch mapping có thể cần gọi service hoặc repository bất đồng bộ. Spring for GraphQL hỗ trợ các kiểu trả về bất đồng bộ tương ứng với cơ chế data fetcher.

Ví dụ với `Mono`:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    return authorService.findForBooksReactive(books);
}
~~~

Hoặc với `CompletableFuture`:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public CompletableFuture<Map<Book, Author>> author(List<Book> books) {
    return authorService.findForBooksAsync(books);
}
~~~

Kiểu trả về cần phù hợp với stack của ứng dụng. Nếu repository reactive, giữ pipeline reactive. Nếu dùng blocking repository, cần chạy I/O trên executor hoặc scheduler phù hợp; không chặn event-loop thread.

Không gọi `.block()`, `.join()` hoặc `.get()` một cách tùy tiện trong batch mapping vì có thể làm mất lợi ích bất đồng bộ và gây nghẽn thread.

## 9. Field name có ảnh hưởng đến DataLoader như thế nào?

Spring dùng `@BatchMapping` để tạo DataLoader tương ứng cho field đã ánh xạ. Tên field và type xác định mapping mà GraphQL engine sẽ dùng khi phân giải nested field.

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Method này xử lý `Book.author`. Nếu client query:

~~~graphql
query {
    books {
        title
        author {
            id
            name
        }
    }
}
~~~

GraphQL gọi batch mapping cho field author của các Book trong kết quả books.

Nếu method vô tình ánh xạ thành `Book.authors`, nhưng SDL chỉ có `Book.author`, client vẫn không thể sử dụng mapping đó cho field author. `@BatchMapping` không đổi tên field trong SDL và cũng không sửa operation của client.

Vì vậy, khi resolver không được gọi, cần kiểm tra tọa độ type/field trước khi điều tra DataLoader hoặc repository.

## 10. Phân biệt @BatchMapping với @SchemaMapping

Hai annotation đều ánh xạ method vào field của GraphQL object type, nhưng cách xử lý source khác nhau.

### @SchemaMapping xử lý một source object

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Method nhận một Book và thường tải Author cho Book đó.

### @BatchMapping xử lý một nhóm source object

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Method nhận danh sách Book và tải Author cho cả nhóm.

Không nên đăng ký đồng thời `@SchemaMapping` và `@BatchMapping` cho cùng tọa độ `Book.author` nếu không có một thiết kế đặc biệt rõ ràng. Cả hai cùng muốn xử lý một field và có thể gây mapping xung đột hoặc hành vi khó dự đoán.

`@BatchMapping` phù hợp khi có thể tải dữ liệu theo nhóm. `@SchemaMapping` phù hợp với field cần logic riêng cho một source object hoặc không cần batching.

## 11. Các lỗi naming mismatch thường gặp

Một số lỗi phổ biến xuất phát từ việc tên method, field và type không đồng nhất.

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Resolver không chạy cho `Book.author` | Method tên `authors`, annotation không có `field`. | Đổi method thành `author` hoặc đặt `field = "author"`. |
| Field không được ánh xạ dù tên method đúng | Type nguồn bị suy luận sai. | Đặt `typeName = "Book"` và kiểm tra kiểu source parameter. |
| Mapping không khớp schema | Dùng tên class Java thay cho GraphQL type name. | Dùng đúng tên type trong SDL. |
| Field có chữ hoa/thường khác nhau | GraphQL phân biệt hoa thường. | Dùng đúng tên field theo SDL. |
| Method có raw List | Không có generic source type để suy luận rõ ràng. | Dùng `List<Book>` và khai báo `typeName` nếu cần. |
| Map trả về không có kết quả | Key map không phải source object tương ứng. | Dùng `Map<Book, Author>` với key là Book trong batch. |
| List trả sai field | Kết quả list không cùng thứ tự source object. | Sắp xếp kết quả theo thứ tự đầu vào hoặc dùng Map. |
| Hai method cùng ánh xạ một tọa độ | Mapping bị đăng ký trùng. | Giữ một batch mapping rõ ràng cho mỗi type/field. |

## 12. Kiểm thử tên field của @BatchMapping

Nên kiểm thử operation thực tế gọi đúng field trong SDL. Ví dụ:

~~~graphql
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
~~~

Batch mapping:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findForBooks(books);
}
~~~

Test với GraphQlTester:

~~~java
@Test
void resolvesAuthorFieldUsingExplicitFieldName() {
    graphQlTester.document("""
            query {
                books {
                    title
                    author {
                        name
                    }
                }
            }
            """)
        .execute()
        .path("books[0].author.name")
        .entity(String.class)
        .isEqualTo("Ada");
}
~~~

Test này xác nhận field `Book.author` được phân giải thông qua mapping đã chỉ định rõ `field = "author"` dù tên method là `loadAuthors`.

Nên kiểm thử thêm:

- Mapping mặc định khi tên method trùng field.
- Mapping tường minh khi method name khác field name.
- Type name được suy luận từ `List<Book>`.
- Type name được khai báo rõ khi GraphQL type khác Java class name.
- Hai object type có field trùng tên nhưng resolver được phân biệt bằng typeName.
- Map có đủ key cho source object.
- List giữ đúng thứ tự source object.
- Source object không có dữ liệu liên quan.
- Batch mapping trả kết quả bất đồng bộ.
- Không có hai resolver đăng ký trùng cùng tọa độ.

Một test chỉ gọi method Java trực tiếp không đủ xác nhận Spring đã đăng ký đúng field. Cần chạy operation qua GraphQlTester để kiểm tra toàn bộ schema và mapping.

## 13. Quy trình đặt tên và triển khai batch mapping

Khi thêm batch mapping mới, có thể làm theo trình tự:

1. Xác định GraphQL object type chứa field cần batch.
2. Kiểm tra chính xác tên type và field trong SDL.
3. Chọn tên method Java trùng field nếu muốn dùng suy luận mặc định.
4. Nếu tên method khác, khai báo `field` rõ ràng.
5. Nếu type không thể suy luận rõ từ source parameter, khai báo `typeName`.
6. Dùng `List<SourceType>` làm tham số nguồn với generic cụ thể.
7. Chọn `Map<SourceType, Value>` hoặc `List<Value>` và bảo đảm ghép kết quả chính xác.
8. Trả kiểu bất đồng bộ phù hợp nếu service cần I/O.
9. Kiểm tra không có mapping khác trùng cùng type/field.
10. Viết GraphQlTester để xác nhận operation gọi đúng field.
11. Kiểm tra số lần batch và dữ liệu trả về khi có nhiều source object.

## 14. Những điểm cần ghi nhớ

- `@BatchMapping` ánh xạ một nhóm source object vào một field của GraphQL object type.
- Mặc định, tên method là tên field GraphQL.
- Method `authors` không tự động ánh xạ vào field `author`; cần đổi tên hoặc dùng `field = "author"`.
- `typeName` có thể được suy ra từ generic source parameter; khai báo tường minh khi type Java và GraphQL khác nhau hoặc cần làm rõ mapping.
- Tên GraphQL type và field phải khớp chính xác với SDL, kể cả chữ hoa/thường.
- Source parameter nên có kiểu generic cụ thể như `List<Book>`.
- `Map<Source, Value>` ghép theo source object; `List<Value>` phải giữ đúng thứ tự source.
- Có thể trả kết quả bất đồng bộ nếu phù hợp với service/repository.
- Tránh đăng ký `@SchemaMapping` và `@BatchMapping` cùng một tọa độ nếu không có chủ đích.
- Dùng GraphQlTester để xác nhận mapping thực sự được kết nối với field SDL.

Quy tắc field name của `@BatchMapping` khá trực tiếp: tên method là tên field theo mặc định, còn `field` cho phép khai báo tên GraphQL rõ ràng khi cần. Khi kết hợp đúng `typeName`, source generic và kiểu trả về, Spring for GraphQL có thể ghép batch result vào đúng field mà client yêu cầu.

