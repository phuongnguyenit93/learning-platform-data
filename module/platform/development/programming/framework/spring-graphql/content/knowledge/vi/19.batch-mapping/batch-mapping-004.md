# Map source sang target với @BatchMapping

Trong GraphQL, một field lồng nhau thường lấy dữ liệu dựa trên object cha. Ví dụ, field `Book.author` cần nhận một `Book` làm source và trả về một `Author` làm target. Nếu resolver được gọi riêng cho từng cuốn sách, ứng dụng dễ tạo N+1 truy vấn. `@BatchMapping` của Spring for GraphQL cho phép nhận một danh sách source object, tải dữ liệu liên quan theo lô và trả kết quả ánh xạ từ từng source sang target.

Với kiểu trả về `Map<Source, Target>`, key của map là source object mà GraphQL đã chuyển vào batch method; value là giá trị của field cần phân giải cho source đó. Cách tổ chức này không phụ thuộc thứ tự kết quả từ repository, miễn là mỗi source được liên kết đúng với target. Đây là nội dung cốt lõi của pattern “map source sang target”.

Sau bài này, bạn có thể:

- Hiểu source object và target value trong một batch mapping.
- Khai báo `@BatchMapping` cho field quan hệ trong SDL.
- Trả `Map<Source, Target>` hoặc `Mono<Map<Source, Target>>` đúng hợp đồng.
- Truy vấn target theo tập khóa và dựng lại map theo source object.
- Xử lý quan hệ một-một, nhiều-một và một-nhiều.
- Phân biệt map theo source với list/Flux phải giữ thứ tự.
- Xử lý target không tồn tại, source equality, lỗi và quyền truy cập.
- Kiểm thử mapping và xác nhận batch thực sự giảm số lần truy cập backend.

## 1. Source và target trong field mapping

Giả sử schema có sách và tác giả:

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

Khi GraphQL phân giải field `Book.author`, object `Book` hiện tại là **source**. Giá trị `Author` trả về là **target** của field đó.

```graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
```

Nếu query trả về 50 sách, GraphQL có thể cần 50 giá trị `author`. `@BatchMapping` gom 50 source `Book` vào một lần gọi batch method. Method tìm các tác giả cần thiết và trả map để GraphQL biết mỗi sách nhận tác giả nào.

Source không nhất thiết là entity JPA. Đó là object cha mà resolver trước đó trả về cho GraphQL, có thể là record, DTO, projection hoặc domain object. Kiểu Java của source method parameter phải nhận được các object thực tế đó.

## 2. Hợp đồng của @BatchMapping

Khai báo một batch mapping cho `Book.author`:

```java
@Controller
public class BookController {

    @BatchMapping(typeName = "Book", field = "author")
    public Map<BookView, AuthorView> author(List<BookView> books) {
        // Phần triển khai đầy đủ được trình bày ở mục 5.
        throw new UnsupportedOperationException("Illustrative signature");
    }
}
```

Các thành phần quan trọng:

- `typeName = "Book"`: tên object type trong GraphQL SDL.
- `field = "author"`: field cần batch mapping.
- `List<BookView> books`: danh sách source object được gom cho field đó.
- `Map<BookView, AuthorView>`: key là source `BookView`, value là target `AuthorView` cho field `author`.

Spring for GraphQL đăng ký batch data fetcher tương ứng với field. Thay vì gọi method một lần cho từng `Book`, framework gom các source object rồi gọi batch method. Method phải trả kết quả có thể ghép chính xác về từng source.

Tên GraphQL trong `typeName` và `field` phải khớp schema. Tên class Java có thể khác tên GraphQL type; ví dụ GraphQL `Book` có thể được biểu diễn bằng Java `BookView`.

## 3. Vì sao trả Map<Source, Target>?

Batch method có thể trả về một danh sách target theo thứ tự source đầu vào, hoặc trả map từ source sang target. Map hữu ích khi thứ tự dữ liệu từ database không giống thứ tự source, hoặc một số target có thể không tồn tại.

Ví dụ source list:

```text
books = [Book-A(authorId=30), Book-B(authorId=10), Book-C(authorId=20)]
```

Repository có thể trả tác giả theo thứ tự riêng:

```text
authors = [Author-10, Author-20, Author-30]
```

Nếu chỉ trả list theo thứ tự repository, GraphQL có thể gán nhầm tác giả cho sách. Map biểu diễn quan hệ rõ ràng:

```text
Book-A -> Author-30
Book-B -> Author-10
Book-C -> Author-20
```

Map không yêu cầu thứ tự phần tử. Mỗi target được liên kết với source object tương ứng qua key. Điều này giúp batch method tập trung vào việc tra cứu target theo khóa và sau đó dựng lại quan hệ source-to-target.

## 4. Chuẩn bị Java source và target model

Ví dụ dùng record làm read model:

```java
public record BookView(
        Long id,
        String title,
        Long authorId) {
}

public record AuthorView(
        Long id,
        String name) {
}
```

Root resolver trả về source object:

```java
@Controller
public class CatalogQueryController {

    private final BookService bookService;

    public CatalogQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<BookView> books() {
        return bookService.findBooks();
    }
}
```

Khi GraphQL thực thi field `author` trên từng `BookView`, Spring gom các source object và chuyển list đó vào batch method. `authorId` là khóa liên kết tới target, nhưng key của map kết quả vẫn là `BookView`, vì GraphQL cần biết target nào thuộc source nào.

## 5. Triển khai map source sang target

Service tải nhiều tác giả trong một lần và trả map theo ID:

```java
@Service
public class AuthorService {

    private final AuthorRepository authorRepository;

    public AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    public Map<Long, AuthorView> findByIds(Set<Long> authorIds) {
        Iterable<AuthorEntity> entities = authorRepository.findAllById(authorIds);

        return StreamSupport.stream(entities.spliterator(), false)
                .collect(Collectors.toMap(
                        AuthorEntity::getId,
                        entity -> new AuthorView(entity.getId(), entity.getName())));
    }
}
```

Batch mapping chuyển map theo ID thành map theo source:

```java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<BookView, AuthorView> author(List<BookView> books) {
        Set<Long> authorIds = books.stream()
                .map(BookView::authorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<Long, AuthorView> authorsById = authorService.findByIds(authorIds);

        Map<BookView, AuthorView> result = new HashMap<>();
        for (BookView book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

Có hai bước tra cứu riêng:

1. Lấy tập `authorId` duy nhất và gọi service một lần để tải các target.
2. Duyệt lại từng source `BookView`, tìm target theo `authorId` rồi thêm cặp source-target vào map kết quả.

Repository có thể trả dữ liệu theo bất kỳ thứ tự nào. Vì `authorsById` được lập chỉ mục theo ID, bước dựng map cuối cùng vẫn ghép đúng tác giả với từng cuốn sách.

Trong ví dụ, `authorId` có thể null vì schema khai báo `author: Author` nullable và dữ liệu sách có thể chưa gắn tác giả. Nếu `authorId` luôn bắt buộc, có thể bỏ bước lọc null và củng cố invariant ở model/service.

## 6. Vì sao key kết quả phải là source object?

Một nhầm lẫn thường gặp là trả `Map<Long, AuthorView>` vì `Long` là ID của sách. Nhưng `@BatchMapping` cần liên kết giá trị field với từng source object đã nhận. Với field `Book.author`, map kết quả phải dùng source `BookView` làm key:

```java
Map<BookView, AuthorView> result;
```

Map theo ID có thể là cấu trúc trung gian để tra cứu target:

```java
Map<Long, AuthorView> authorsById;
```

Sau đó phải chuyển nó thành map source-to-target. Không trả map trung gian nếu key của nó không phải source type mà batch method nhận.

Phân biệt ba kiểu key:

| Map | Vai trò | Có phải kết quả source-to-target của `@BatchMapping`? |
| --- | --- | --- |
| `Map<Long, AuthorView>` | Tra cứu target theo `authorId` | Không, thường chỉ là map trung gian |
| `Map<BookView, AuthorView>` | Ghép mỗi source book với target author | Có |
| `Map<AuthorView, BookView>` | Ghép ngược author sang book | Không phù hợp với field `Book.author` |

Quy tắc này thay đổi theo field đang batch. Nếu field là `Author.books`, source sẽ là `AuthorView` và target là danh sách `BookView`; khi đó kết quả phù hợp có thể là `Map<AuthorView, List<BookView>>`.

## 7. Dùng Map cho quan hệ một-nhiều

`@BatchMapping` không chỉ dùng cho quan hệ một-một hoặc nhiều-một. Nếu một source có nhiều target, value trong map có thể là collection.

Schema:

```graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}
```

Java batch method:

```java
@BatchMapping(typeName = "Author", field = "books")
public Map<AuthorView, List<BookView>> books(List<AuthorView> authors) {
    Set<Long> authorIds = authors.stream()
            .map(AuthorView::id)
            .collect(Collectors.toSet());

    Map<Long, List<BookView>> booksByAuthorId = bookService.findByAuthorIds(authorIds);

    Map<AuthorView, List<BookView>> result = new HashMap<>();
    for (AuthorView author : authors) {
        result.put(
                author,
                booksByAuthorId.getOrDefault(author.id(), List.of()));
    }
    return result;
}
```

Ở đây source là `AuthorView`, target là `List<BookView>`. Map cuối cùng vẫn có key là source object, nhưng value là danh sách target. Nếu tác giả chưa có sách, trả `List.of()` phù hợp với schema `[Book!]!` hơn là null.

Đối với quan hệ nhiều-nhiều, service có thể truy vấn bảng liên kết theo tập source ID, group các target theo source ID rồi dựng `Map<Source, List<Target>>` tương tự.

## 8. Map source-to-target khác với list theo thứ tự

Spring for GraphQL hỗ trợ các kiểu kết quả batch khác nhau. Hai cách thường gặp là:

| Kiểu trả về | Cách ghép kết quả | Yêu cầu chính |
| --- | --- | --- |
| `Map<Source, Target>` | Ghép theo key source object | Mỗi source cần có mapping đúng |
| `List<Target>` hoặc `Flux<Target>` | Ghép theo vị trí source đầu vào | Kết quả phải giữ đúng thứ tự và số lượng tương ứng |

Ví dụ source list `[Book-A, Book-B, Book-C]`:

**Map:**

```java
Map<BookView, AuthorView> result = new HashMap<>();
result.put(bookA, author30);
result.put(bookB, author10);
result.put(bookC, author20);
```

**List:**

```java
List<AuthorView> result = List.of(author30, author10, author20);
```

List phải có thứ tự tương ứng `[Book-A, Book-B, Book-C]`. Nếu repository trả `[author10, author20, author30]` mà method trả trực tiếp, dữ liệu sẽ bị gán sai. Map tránh yêu cầu thứ tự đó vì mỗi target được nối với source bằng key.

Khi target có thể vắng mặt, list cần giữ đúng vị trí bằng null nếu hợp đồng loader cho phép; không lọc bỏ phần tử null vì việc đó làm lệch vị trí các source tiếp theo. Với map, có thể không có entry cho source không có target; khi đó field được phân giải thành null theo semantics mapped loader. Hãy kiểm tra nullability của field trong SDL.

## 9. Dùng Map với source object và equals/hashCode

Map trong Java dùng `equals` và `hashCode` để tìm key. Vì vậy, các key trong map kết quả phải tương ứng với source object mà framework đang xử lý.

Với record như `BookView`, Java tự tạo `equals` và `hashCode` dựa trên các thành phần record. Khi batch method nhận list `books`, dùng chính các object trong list làm key là cách rõ ràng:

```java
Map<BookView, AuthorView> result = new HashMap<>();
for (BookView book : books) {
    result.put(book, authorsById.get(book.authorId()));
}
```

Không nên tự tạo một `new BookView(...)` khác để làm key nếu equality của source type không bảo đảm hai instance tương đương. Với entity JPA, hãy cẩn thận khi `equals/hashCode` dựa trên ID chưa được sinh, field mutable hoặc proxy. Thay đổi hash code sau khi đưa object vào `HashMap` có thể làm entry không còn truy cập được.

Nếu cần mapping theo ID vì source object có equality phức tạp, có thể dùng `DataLoader` hoặc một abstraction batch khác với key ID rõ ràng. Nhưng với `@BatchMapping`, kết quả phải tuân theo hợp đồng mapping source của framework; không thay key source bằng ID một cách tùy ý.

## 10. Target không tồn tại và nullability

Giả sử một sách tham chiếu `authorId` không còn tồn tại. Có một số cách xử lý:

- Trả null cho field `author` nếu quan hệ có thể vắng mặt.
- Trả một target fallback nếu domain thực sự định nghĩa đối tượng thay thế.
- Ném lỗi nếu dữ liệu tham chiếu sai là vi phạm invariant cần được báo cáo.

Với schema:

```graphql
type Book {
    author: Author
}
```

field `author` nullable, nên target không tồn tại có thể được biểu diễn bằng null. Nếu schema khai báo `author: Author!`, null không hợp lệ; GraphQL sẽ tạo execution error và áp dụng null propagation lên field cha gần nhất cho phép null.

Trong map kết quả, có thể thêm key với value null khi dùng `HashMap`, hoặc không thêm entry cho source đó. Cả hai cách biểu diễn đều cần được kiểm thử theo semantics của loader và phiên bản framework. Không dùng `Map.of(...)` nếu cần chứa value null vì factory này từ chối null.

Đối với quan hệ một-nhiều, nếu schema khai báo `[Book!]!`, nên trả list rỗng khi không có sách thay vì null. Giá trị rỗng và giá trị không tồn tại có ý nghĩa khác nhau.

## 11. Source có target ID null hoặc không hợp lệ

Trước khi truy vấn, batch method cần xác định source nào có khóa hợp lệ:

```java
Set<Long> authorIds = books.stream()
        .map(BookView::authorId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());
```

Sau đó khi dựng kết quả:

```java
for (BookView book : books) {
    AuthorView author = book.authorId() == null
            ? null
            : authorsById.get(book.authorId());
    result.put(book, author);
}
```

Không đưa null vào tập ID truy vấn nếu repository không hỗ trợ hoặc query sẽ không có ý nghĩa. Nếu source có ID sai định dạng, dữ liệu bất nhất hoặc vi phạm invariant, quyết định xử lý cần nhất quán với domain. Đừng âm thầm gán một target mặc định cho tất cả source lỗi.

## 12. Reactive source-to-target mapping

Trong ứng dụng WebFlux hoặc service trả về publisher, batch method có thể trả `Mono<Map<Source, Target>>`:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<BookView, AuthorView>> author(List<BookView> books) {
    Set<Long> authorIds = books.stream()
            .map(BookView::authorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

    return authorService.findByIds(authorIds)
            .map(authorsById -> {
                Map<BookView, AuthorView> result = new HashMap<>();
                for (BookView book : books) {
                    result.put(book, authorsById.get(book.authorId()));
                }
                return result;
            });
}
```

Giả sử `authorService.findByIds` trả `Mono<Map<Long, AuthorView>>`. Mapping được tạo sau khi service hoàn tất và vẫn dùng source object làm key.

Với service blocking như JPA/JDBC, có thể trả `Map` đồng bộ trong ứng dụng Spring MVC. Trong WebFlux, không gọi `.block()` bên trong batch method; hãy dùng repository reactive hoặc cô lập lời gọi blocking ở scheduler/executor có giới hạn.

## 13. Batching thực sự phải xảy ra ở service/repository

`@BatchMapping` gom source object, nhưng không tự động làm một truy vấn SQL duy nhất. Service cần nhận tập ID và truy vấn theo lô:

```java
public Map<Long, AuthorView> findByIds(Set<Long> ids) {
    Iterable<AuthorEntity> entities = authorRepository.findAllById(ids);
    return StreamSupport.stream(entities.spliterator(), false)
            .collect(Collectors.toMap(
                    AuthorEntity::getId,
                    authorMapper::toView));
}
```

Nếu batch method lặp source rồi gọi `findById` cho từng phần tử, N+1 vẫn còn:

```java
// Không nên: vẫn phát sinh một truy vấn cho mỗi source.
for (BookView book : books) {
    AuthorView author = authorService.findById(book.authorId());
    result.put(book, author);
}
```

Hãy kiểm tra SQL hoặc số lần service/repository được gọi. Một method có tên `findByIds` chưa đủ chứng minh nó batch; cần xem triển khai bên trong có thực sự dùng một truy vấn nhiều ID, một bulk endpoint hoặc một cơ chế tải theo lô hay không.

Nếu danh sách source lớn, có thể cần chia tập ID thành nhiều chunk để tránh giới hạn bind parameter hoặc query quá nặng. `@BatchMapping` có thể được cấu hình giới hạn batch size theo API phiên bản Spring for GraphQL; khi cần, kiểm tra thuộc tính `maxBatchSize` của annotation trong phiên bản dự án.

## 14. Source trùng target và target dùng chung

Nhiều source có thể cùng trỏ đến một target. Ví dụ, 30 cuốn sách cùng một tác giả. Service nên loại ID trùng khi truy vấn:

```java
Set<Long> authorIds = books.stream()
        .map(BookView::authorId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());
```

Sau đó map từng source về cùng một `AuthorView`:

```text
Book-A -> Author-7
Book-B -> Author-7
Book-C -> Author-7
```

Map source-to-target cho phép nhiều key cùng có value giống nhau. Điều này không làm mất source nào vì key vẫn là từng `BookView`. Tránh chuyển kết quả thành map `AuthorView -> BookView`, vì kiểu map đó chỉ giữ một sách cho mỗi tác giả và làm mất quan hệ nhiều-một.

Nếu hai source object bằng nhau theo `equals`, một map thông thường chỉ giữ một entry cho key đó. Hãy bảo đảm source key có semantics equality phù hợp với từng source trong batch. Với source DTO đại diện mỗi bản ghi duy nhất, equality theo ID thường hợp lý; với entity/proxy, hãy rà soát triển khai equality trước khi dùng làm key.

## 15. Authorization và request context

Một batch có thể chứa source thuộc nhiều tenant hoặc phạm vi quyền khác nhau. Không được giả định rằng vì các source nằm trong cùng một batch nên người gọi có quyền xem tất cả target.

Service hoặc repository phải áp dụng authorization theo caller và từng resource. Ví dụ, nếu một số tác giả thuộc tenant khác, truy vấn bulk cần lọc theo tenant đã xác thực hoặc kiểm tra quyền trước khi đưa target vào map.

Không nhận tenant ID từ `authorId` hoặc một field client tự gửi rồi dùng nó làm bằng chứng quyền truy cập. Caller identity và tenant context phải đến từ security context/request context đáng tin cậy. Nếu batch loader cần context, hãy truyền qua cơ chế context phù hợp của Spring for GraphQL hoặc service security boundary.

Nếu chỉ một số source không được phép truy cập, cần quyết định trả null, lỗi theo từng field hay từ chối toàn bộ batch. Lựa chọn này phải phù hợp với chính sách bảo mật và không để lộ việc một resource có tồn tại hay không ngoài ý muốn.

## 16. Kiểm thử Map source sang target

Kiểm thử cần xác nhận cả kết quả mapping và khả năng ghép đúng source-target khi thứ tự repository khác thứ tự source.

Ví dụ query:

```graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
```

Với `GraphQlTester`:

```java
graphQlTester.document("""
        query {
            books {
                id
                author {
                    id
                    name
                }
            }
        }
        """)
    .execute()
    .path("books[0].author.name")
    .entity(String.class)
    .isEqualTo("Author for Book A");
```

Các test quan trọng:

1. Nhiều source được gom vào một lần gọi batch method.
2. Repository trả target theo thứ tự khác source nhưng map vẫn ghép đúng.
3. Nhiều source cùng trỏ một target đều nhận đúng target.
4. Source có target ID null được xử lý theo semantics đã chọn.
5. Target không tồn tại tạo null hoặc lỗi phù hợp nullability.
6. Quan hệ một-nhiều trả đúng danh sách cho từng source.
7. Source object dùng làm key map có equality/hashCode ổn định.
8. Authorization và tenant filtering áp dụng cho toàn bộ batch.
9. Service/repository được gọi theo lô, không phải một lần cho mỗi source.
10. Reactive method không block và hoàn tất đúng response.

Chỉ kiểm tra response đúng chưa đủ chứng minh batch hoạt động. Dùng spy/mock hoặc instrumentation để xác nhận số lần gọi service/repository và số key trong mỗi batch.

## 17. Những lỗi thường gặp

- **Trả `Map<ID, Target>` thay cho `Map<Source, Target>`:** GraphQL cần map theo source object; map ID thường chỉ là cấu trúc trung gian.
- **Dùng target làm key:** đảo chiều quan hệ và có thể làm mất nhiều source cùng trỏ một target.
- **Trả list theo thứ tự repository:** target có thể bị gán nhầm source. Dùng map hoặc sắp lại đúng thứ tự source.
- **Lọc bỏ target null khỏi list:** làm lệch vị trí nếu dùng kiểu trả về theo thứ tự.
- **Dùng source object mới làm map key:** equality không tương thích có thể khiến framework không tìm được mapping.
- **Không xem xét equals/hashCode của entity:** mutable ID hoặc proxy có thể làm map key không ổn định.
- **Truy vấn một lần cho từng source bên trong batch method:** N+1 vẫn tồn tại.
- **Bỏ qua source có target ID null:** có thể thiếu key và khiến field trả kết quả không theo dự kiến.
- **Dùng Map.of khi cần value null:** `Map.of` không cho phép null key/value.
- **Không xử lý target vắng mặt:** field non-null có thể gây null propagation ngoài dự kiến.
- **Bỏ qua authorization theo từng resource:** một batch có thể chứa dữ liệu từ nhiều phạm vi quyền.
- **Đăng ký cả @SchemaMapping và @BatchMapping cho cùng field:** có thể tạo data fetcher trùng coordinate.

## 18. Quy trình triển khai source-to-target batch mapping

Khi cần tải target cho nhiều source object, hãy thực hiện:

1. Xác định field GraphQL và source object type, ví dụ `Book.author`.
2. Khai báo `@BatchMapping(typeName = "Book", field = "author")`.
3. Nhận `List<Source>` và xác định khóa dùng để tìm target.
4. Loại khóa null hoặc trùng lặp theo semantics nghiệp vụ.
5. Gọi service/repository bulk để tải target theo tập khóa.
6. Lập map trung gian theo target ID nếu cần.
7. Duyệt lại source list và dựng `Map<Source, Target>` bằng chính source object nhận được.
8. Quyết định target thiếu/null và bảo đảm khớp nullability trong SDL.
9. Kiểm tra equality/hashCode của source key và quyền truy cập trên từng target.
10. Kiểm thử thứ tự, source trùng target, target vắng mặt và số lần truy vấn backend.

Map source sang target là cách biểu diễn rõ ràng cho batch field trong Spring for GraphQL. Source object làm key, target field value làm value; service có thể tra cứu target theo ID rồi batch method dựng lại map theo source. Khi dùng đúng key, xử lý target vắng mặt theo schema và thực hiện bulk query thật sự, `@BatchMapping` giúp field lồng nhau vừa ghép dữ liệu chính xác vừa tránh N+1 mà không phụ thuộc thứ tự kết quả từ repository.

## Tài liệu tham khảo

- [Spring for GraphQL — Batch Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — BatchLoaderRegistry](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [GraphQL Java — DataLoader batching](https://www.graphql-java.com/documentation/batching/)
- [GraphQL Specification — Field Execution](https://spec.graphql.org/October2021/#sec-Field-Execution)
