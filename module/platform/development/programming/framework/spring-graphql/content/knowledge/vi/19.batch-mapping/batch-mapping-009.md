# Khi cần BatchLoaderRegistry thay vì @BatchMapping

Trong Spring for GraphQL, `@BatchMapping` và `BatchLoaderRegistry` đều giúp gom các lần tải dữ liệu thành batch để giảm N+1. Chúng không phải hai cơ chế cạnh tranh hoàn toàn: **`@BatchMapping` là cách khai báo gọn cho một field cụ thể, còn `BatchLoaderRegistry` cho phép đăng ký DataLoader tường minh để resolver chủ động gọi theo key và tái sử dụng loader ở nhiều nơi.**

Với quan hệ đơn giản như `Book.author`, một phương thức `@BatchMapping` thường là đủ. Khi cùng một loại dữ liệu được tải từ nhiều parent type, khi resolver cần gọi loader theo ID hoặc composite key, khi cần kiểm soát cache/options/context, hoặc khi một loader được dùng ở nhiều field khác nhau, đăng ký qua `BatchLoaderRegistry` thường phù hợp hơn.

## 1. @BatchMapping đã dùng DataLoader bên dưới

Giả sử schema có danh sách sách và field tác giả:

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

Nếu mỗi lần resolve `Book.author` đều gọi repository riêng, một query lấy 30 quyển sách có thể tạo một truy vấn lấy sách và 30 truy vấn lấy tác giả. `@BatchMapping` cho phép nhận tất cả source object trong một lần gọi và tải tác giả theo nhóm:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<Long, Author> authorsById = authorService.findAllByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

Spring for GraphQL đăng ký cơ chế batch tương ứng cho field `Book.author`. Ở runtime, các yêu cầu được điều phối qua DataLoader. Vì vậy, dùng `@BatchMapping` không có nghĩa là bỏ qua DataLoader; annotation này che bớt phần đăng ký loader và ánh xạ kết quả về source object.

`@BatchMapping` thường nhận `List<Book>` và có thể trả về `Map<Book, Author>` để ánh xạ theo source, hoặc trả về `List<Author>` với thứ tự kết quả tương ứng thứ tự source đầu vào. Khi dùng list, batch method phải bảo đảm đúng số lượng và thứ tự; khi kết quả được tìm theo ID và repository không giữ thứ tự, Map thường dễ kiểm soát hơn.

## 2. BatchLoaderRegistry giải quyết phần nào?

`BatchLoaderRegistry` là abstraction của Spring for GraphQL để đăng ký định nghĩa batch loader. Spring dùng các định nghĩa đó để tạo `DataLoader` và đưa vào `DataLoaderRegistry` của từng GraphQL execution/request.

Có ba thành phần cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| `BatchLoaderRegistry` | Nơi ứng dụng đăng ký cách tải dữ liệu theo batch trong cấu hình Spring |
| `DataLoaderRegistry` | Registry runtime chứa các DataLoader instance của một GraphQL execution |
| `DataLoader<K, V>` | API resolver gọi `load(key)` để nhận future của value; loader gom key và cache theo cấu hình |

`BatchLoaderRegistry` thường được Spring quản lý như một bean dùng để đăng ký loader. DataLoader instance và cache thực tế được tạo theo request. Không nên tự tạo một DataLoader singleton rồi chia sẻ giữa các request; cache có thể giữ dữ liệu cũ hoặc làm lộ dữ liệu giữa các user/tenant.

Ví dụ đăng ký một mapped batch loader:

```java
@Configuration
public class DataLoaderConfiguration {

    public DataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIdsAsync(authorIds));
    }
}
```

`forTypePair(Long.class, Author.class)` mô tả key/value type. Batch function nhận một tập author ID và trả về `CompletionStage<Map<Long, Author>>`. Map không cần theo thứ tự key đầu vào vì mỗi kết quả được ghép lại bằng key. Nếu một ID không có trong Map, loader không có value cho key đó; cần xác định field GraphQL có cho phép `null` hay không.

Resolver lấy DataLoader và gọi theo ID:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
```

Resolver không gọi repository trực tiếp và cũng không `join()` future. GraphQL Java phối hợp dispatch các key trong execution; Spring tích hợp DataLoader với vòng đời request.

## 3. Trường hợp thứ nhất: nhiều parent type cần cùng một dữ liệu

Đây là lý do thường gặp nhất để dùng `BatchLoaderRegistry`. Giả sử cả `Book` và `Review` đều có tác giả. Nếu chỉ dùng `@BatchMapping`, ta có thể viết hai batch method riêng:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> bookAuthors(List<Book> books) {
    // Tải author cho danh sách Book.
}

@BatchMapping(typeName = "Review", field = "author")
public Map<Review, Author> reviewAuthors(List<Review> reviews) {
    // Tải author cho danh sách Review.
}
```

Hai method này cùng thực hiện một nghiệp vụ: tải `Author` theo ID. Tuy nhiên, mỗi mapping có thể tạo batch riêng. Nếu cùng một GraphQL operation yêu cầu cả `Book.author` và `Review.author`, ta muốn các key tác giả được gom vào một loader chung.

Đăng ký một loader theo cặp `Long -> Author`:

```java
@Configuration
public class AuthorLoaderConfiguration {

    public AuthorLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIdsAsync(authorIds));
    }
}
```

Hai resolver ở hai controller khác nhau cùng sử dụng loader đó:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {
        return authorLoader.load(book.authorId());
    }
}
```

```java
@Controller
public class ReviewController {

    @SchemaMapping(typeName = "Review", field = "author")
    public CompletableFuture<Author> author(
            Review review,
            DataLoader<Long, Author> authorLoader) {
        return authorLoader.load(review.authorId());
    }
}
```

Khi các resolver cùng gọi loader trong một execution, các author ID có thể được gom vào cùng batch. Nếu nhiều object có cùng ID, cache theo request còn có thể tránh tải cùng tác giả nhiều lần. Đây là lợi ích khó đạt được nếu mỗi parent field tự có một batch mapping độc lập.

## 4. Trường hợp thứ hai: resolver cần tải theo key thay vì theo source object

`@BatchMapping` được thiết kế quanh một field và danh sách source object của field đó. Trong khi đó, nhiều resolver cần tải dữ liệu theo một key độc lập, ví dụ:

- Lấy `Author` theo `authorId`.
- Lấy `Inventory` theo `productId`.
- Lấy quyền theo `userId` và `resourceId`.
- Lấy tỷ giá theo cặp tiền tệ.
- Lấy bản dịch theo `messageKey` và `locale`.

Ví dụ, `Book` và `Review` đều có `authorId`, nhưng loader chỉ quan tâm ID. Resolver không cần tạo một batch method riêng để ánh xạ từng loại source object; nó chỉ gọi `authorLoader.load(authorId)`.

Với key phức hợp, dùng một kiểu key có `equals` và `hashCode` ổn định, chẳng hạn Java record:

```java
public record LocalizedKey(String messageKey, Locale locale) {
}
```

Đăng ký loader theo key/value type:

```java
registry.forTypePair(LocalizedKey.class, String.class)
    .registerMappedBatchLoader((keys, environment) ->
        translationService.findAllAsync(keys));
```

Resolver có thể tạo key từ dữ liệu source và context:

```java
@SchemaMapping(typeName = "Product", field = "displayName")
public CompletableFuture<String> displayName(
        Product product,
        DataFetchingEnvironment environment,
        DataLoader<LocalizedKey, String> translationLoader) {

    Locale locale = environment.getGraphQlContext().get("locale");
    return translationLoader.load(
        new LocalizedKey(product.messageKey(), locale));
}
```

Trong trường hợp này, DataLoader cache theo cả `messageKey` và `locale`, vì hai locale có thể trả về hai giá trị khác nhau. Java record cung cấp equality theo component, phù hợp để làm key. Nếu dùng class mutable hoặc key không có equality đúng, cache và việc ghép kết quả có thể sai.

## 5. Trường hợp thứ ba: cùng loader được dùng ở nhiều field hoặc nhiều tầng resolver

Một loader có thể được gọi từ nhiều nơi trong cùng operation, không nhất thiết chỉ từ một quan hệ parent-child. Ví dụ query vừa lấy sách, vừa lấy tác giả riêng, vừa lấy số liệu dashboard có tham chiếu đến tác giả:

```graphql
type Query {
    book(id: ID!): Book
    author(id: ID!): Author
    dashboard: Dashboard!
}

type Book {
    author: Author
}

type Dashboard {
    featuredAuthor: Author
}
```

Nếu các resolver cần tải cùng `Author` theo ID, dùng một DataLoader chung giúp thống nhất batching và cache trong execution. Root resolver `author(id:)`, resolver `Book.author` và resolver `Dashboard.featuredAuthor` có thể cùng gọi `load(id)`.

Điều này hữu ích khi các field được phân tách theo domain/controller nhưng vẫn dùng chung nguồn dữ liệu. Batch loader giữ logic truy vấn tập trung; resolver chỉ chuyển dữ liệu đầu vào thành key và trả future.

Lưu ý, việc gom batch chỉ diễn ra giữa các lệnh `load` được dispatch trong cùng execution cycle. Các field ở những tầng lồng nhau khác nhau có thể tạo các batch ở các vòng khác nhau. DataLoader không gom mọi key của toàn bộ query thành một truy vấn duy nhất bất kể cấu trúc execution.

## 6. Trường hợp thứ tư: cần kiểm soát DataLoaderOptions

`@BatchMapping` phù hợp với cấu hình đơn giản. Khi cần kiểm soát DataLoader cụ thể hơn, đăng ký qua `BatchLoaderRegistry` cho phép cấu hình `DataLoaderOptions` tại nơi đăng ký loader.

Ví dụ giới hạn số key mỗi batch và bật cache:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader(
        (authorIds, environment) -> authorService.findAllByIdsAsync(authorIds),
        options -> options
            .setMaxBatchSize(100)
            .setCachingEnabled(true)
    );
```

Các lựa chọn cần quan tâm:

| Nhu cầu | Cách cấu hình hoặc thiết kế |
| --- | --- |
| Giới hạn số ID gửi vào một truy vấn | `maxBatchSize` để chia tập key lớn thành các batch nhỏ |
| Tránh tải cùng key nhiều lần trong một request | Bật cache theo key; đây thường là hành vi mặc định |
| Key có quy tắc equality đặc biệt | Dùng kiểu key bất biến có `equals`/`hashCode` phù hợp hoặc cấu hình cache key function |
| Batch loader cần context | Nhận `BatchLoaderEnvironment` và đọc context đã được truyền vào execution |
| Cần kiểm soát cache sau mutation | Dùng `clear`, `clearAll` hoặc `prime` trên DataLoader hiện tại |

Tên phương thức và overload cấu hình có thể phụ thuộc phiên bản GraphQL Java/Spring for GraphQL mà dự án sử dụng. Hãy đối chiếu API của dependency đang được Spring Boot quản lý khi triển khai.

`maxBatchSize` không phải giới hạn số object client được phép yêu cầu. Nó chia các key đã thu thập thành những batch nhỏ hơn. Pagination và query complexity vẫn cần được kiểm soát ở schema/API layer.

## 7. Trường hợp thứ năm: cần thao tác cache sau mutation

DataLoader cache kết quả theo key trong một execution. Nếu mutation cập nhật một `Author` rồi một resolver khác trong cùng execution tải lại cùng ID, loader có thể trả object cũ đã cache.

Với DataLoader tường minh, resolver mutation có thể xóa cache và nạp trước kết quả mới:

```java
@MutationMapping
public Author updateAuthor(
        @Argument("input") UpdateAuthorInput input,
        DataLoader<Long, Author> authorLoader) {

    Author updated = authorService.update(input);
    authorLoader.clear(updated.id());
    authorLoader.prime(updated.id(), updated);
    return updated;
}
```

`clear(id)` bỏ kết quả cũ trong cache của loader hiện tại. `prime(id, updated)` thêm kết quả mới nếu key chưa có. Thường cần clear trước vì `prime` không ghi đè một key đã tồn tại.

Đây chỉ là cache trong DataLoader của execution hiện tại. Nếu ứng dụng có cache cấp service hoặc cache phân tán, cần invalidation riêng. Nếu mutation thay đổi dữ liệu được loader khác giữ cache, cần cập nhật hoặc xóa đúng loader đó.

Khi chỉ dùng `@BatchMapping`, việc điều khiển DataLoader instance và cache không trực tiếp như khi inject DataLoader. Nếu use case thường xuyên cần clear/prime hoặc gọi loader ở nhiều resolver, đó là dấu hiệu nên đăng ký loader tường minh qua `BatchLoaderRegistry`.

## 8. Trường hợp thứ sáu: cần truyền context vào batch loader

Batch query đôi khi phải phụ thuộc tenant, user, locale hoặc policy đã xác thực. Ví dụ cùng một `authorId` nhưng tenant khác nhau có thể nhìn thấy các trường dữ liệu khác nhau. Khi đó, batch loader cần nhận context phù hợp để truy vấn dữ liệu đúng phạm vi.

`BatchLoaderRegistry` hỗ trợ đăng ký batch loader có nhận `BatchLoaderEnvironment`. Context của GraphQL execution có thể được truyền đến loader thông qua cơ chế context của Spring for GraphQL/GraphQL Java. Hãy lấy tenant hoặc principal từ context đã được xác thực ở server, không tin giá trị tenant tùy ý do client gửi.

Ví dụ về ý tưởng xử lý:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) -> {
        GraphQLContext graphQLContext = environment.getContext();
        TenantId tenantId = graphQLContext.get("tenantId");
        return authorService.findVisibleAuthors(tenantId, authorIds);
    });
```

Đoạn code minh họa giả định ứng dụng đã đặt `tenantId` vào GraphQL context trước khi thực thi. Cần dùng đúng kiểu context và cách truy xuất tương ứng với phiên bản GraphQL Java/Spring for GraphQL. Không nên lấy context rồi bỏ qua authorization ở service; batch query vẫn phải áp dụng điều kiện tenant và quyền truy cập cho mọi key.

DataLoader cache theo key. Nếu một execution có thể chứa nhiều security scope, key phải bao gồm đủ yếu tố ảnh hưởng đến kết quả, hoặc loader phải được giới hạn trong một scope nhất quán. Không chia sẻ loader/cache giữa các request hoặc tenant.

## 9. Đăng ký loader theo type pair và theo tên

`BatchLoaderRegistry` hỗ trợ đăng ký loader dựa trên cặp key/value type. Đây là lựa chọn tự nhiên khi một cặp kiểu chỉ có một loader tương ứng:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((ids, environment) ->
        authorService.findAllByIdsAsync(ids));
```

Resolver có thể nhận `DataLoader<Long, Author>` trực tiếp như một tham số annotated controller. Spring phân giải loader dựa trên generic key/value type.

Nếu ứng dụng cần nhiều loader có cùng key/value type nhưng mục đích khác nhau, đăng ký theo tên giúp phân biệt. Khi đó resolver có thể lấy loader từ `DataFetchingEnvironment` bằng tên đã đăng ký:

```java
registry.forName("visibleAuthors")
    .registerMappedBatchLoader((authorIds, environment) ->
        authorService.findVisibleAuthors(authorIds));

DataLoader<Long, Author> loader =
    environment.getDataLoader("visibleAuthors");
```

Tên loader phải thống nhất giữa nơi đăng ký và nơi lấy. Chỉ dùng tên riêng khi thực sự cần nhiều loader cùng kiểu hoặc cần phân biệt policy; nếu không, đăng ký theo type pair và inject theo kiểu thường đơn giản hơn. API đăng ký theo tên và cách cấu hình cụ thể cần khớp phiên bản Spring for GraphQL trong dự án.

## 10. Khi nào vẫn nên chọn @BatchMapping?

Không phải cứ có DataLoader là cần đăng ký thủ công. `@BatchMapping` thường là lựa chọn dễ đọc nhất khi:

- Batch chỉ phục vụ đúng một field, chẳng hạn `Book.author`.
- Key tự nhiên là source object của field.
- Resolver nhận danh sách source object và trả Map/list tương ứng.
- Không cần chia sẻ loader với field hoặc parent type khác.
- Không cần truy cập DataLoader trực tiếp để clear/prime hoặc dùng ở nơi khác.
- Cấu hình cache và batch size mặc định đáp ứng nhu cầu.

Ví dụ, nếu chỉ có `Book.reviews` cần tải danh sách review cho từng sách, một `@BatchMapping` trả `Map<Book, List<Review>>` là đủ rõ ràng. Việc tạo một loader tường minh chỉ để thay thế một mapping đơn giản có thể làm tăng số thành phần và tên cần quản lý.

## 11. So sánh hai cách tiếp cận

| Tiêu chí | `@BatchMapping` | `BatchLoaderRegistry` |
| --- | --- | --- |
| Mức trừu tượng | Mapping trực tiếp một GraphQL field | Đăng ký DataLoader theo key/value hoặc tên |
| Đầu vào batch | Danh sách source object của field | Tập key do resolver gọi `load(key)` |
| Ánh xạ kết quả | Map source-to-value hoặc list đúng thứ tự | Loader trả value theo key; mapped loader trả Map theo key |
| Chia sẻ giữa nhiều field/type | Thường cần batch mapping riêng cho mỗi field | Có thể dùng chung một loader trong cùng execution |
| Key phức hợp hoặc key độc lập source | Có thể phải tự chuyển đổi qua source object | Tự nhiên hơn vì resolver chủ động tạo key |
| Dùng ở root và nested resolver | Gắn với một field mapping | Có thể gọi từ nhiều resolver khác nhau |
| Cache clear/prime | Không thao tác trực tiếp như DataLoader được inject | Có thể inject DataLoader và thao tác cache |
| Tùy chỉnh options/context | Phù hợp cấu hình đơn giản | Kiểm soát tường minh hơn khi đăng ký loader |
| Độ phức tạp code | Ít boilerplate | Cần đăng ký loader và gọi `load` trong resolver |

`@BatchMapping` và `BatchLoaderRegistry` đều dựa trên DataLoader. Khác biệt chính là cách mô hình hóa và mức kiểm soát: một bên mô tả batch của field, bên kia mô tả loader theo key có thể được dùng ở nhiều vị trí.

## 12. Những điều cần giữ đúng khi dùng BatchLoaderRegistry

**Giữ registry theo request.** Spring quản lý DataLoader instance theo GraphQL execution. Chỉ đăng ký định nghĩa loader ở bean cấu hình; không lưu DataLoader instance vào field static hoặc singleton rồi dùng chung.

**Không block future.** `load(key)` trả về future. Trả future trực tiếp từ resolver, không gọi `join()` hoặc `get()`; việc block làm mất lợi ích bất đồng bộ và có thể gây nghẽn thread.

**Đảm bảo kết quả khớp key.** Với `BatchLoader`, list phải theo đúng thứ tự key đầu vào. Với `MappedBatchLoader`, Map phải dùng đúng key equality. Chọn mapped loader khi thứ tự nguồn dữ liệu không được bảo đảm.

**Kiểm soát kích thước batch.** Một query lớn có thể tạo ra rất nhiều key. Giới hạn batch size theo database và dịch vụ downstream, đồng thời vẫn giới hạn pagination/depth/complexity ở cấp GraphQL.

**Phân biệt missing data và batch failure.** Không tìm thấy một key có thể là kết quả hợp lệ; lỗi database hoặc HTTP là lỗi thực thi. Đừng biến mọi exception thành Map rỗng vì client sẽ hiểu sai dữ liệu.

**Bảo vệ cache theo scope.** Nếu kết quả phụ thuộc tenant hoặc principal, batch query và key/cache phải phản ánh đúng security scope. Cache của DataLoader không phải nơi thay thế authorization.

## 13. Kiểm thử loader dùng chung

Một test quan trọng cho `BatchLoaderRegistry` là chứng minh hai parent type có thể gọi cùng loader và được gom key trong cùng execution. Ví dụ operation yêu cầu sách và review, cả hai đều lấy tác giả:

```graphql
query {
    books {
        title
        author {
            id
            name
        }
    }
    reviews {
        content
        author {
            id
            name
        }
    }
}
```

Với `GraphQlTester`, kiểm tra cả hai nhánh response. Dùng spy/mock ở `AuthorService` để xác nhận batch loader nhận tập ID tổng hợp theo execution thay vì mỗi resolver gọi một truy vấn riêng. Số batch cụ thể có thể lớn hơn một nếu dispatch chia theo execution level hoặc `maxBatchSize`; test nên xác nhận số lần gọi phù hợp với cấu hình và không giả định toàn query luôn có đúng một batch.

Các trường hợp nên kiểm tra:

- `Book.author` và `Review.author` dùng cùng loader trong một request.
- Hai object cùng author ID không tạo hai lần tải khi cache bật.
- Hai GraphQL request riêng biệt có DataLoader/cache riêng.
- Key không tìm thấy trả `null` đúng theo schema.
- Batch service lỗi được chuyển thành GraphQL error phù hợp.
- `maxBatchSize` chia tập key lớn theo giới hạn cấu hình.
- `clear` và `prime` cập nhật cache sau mutation trong execution hiện tại.
- Tenant hoặc principal không thể đọc dữ liệu ngoài phạm vi được cấp quyền.

Ví dụ test một field bằng `GraphQlTester`:

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
    .path("books")
    .entityList(BookView.class)
    .hasSize(3);
```

Để kiểm tra loader thực sự dùng chung giữa hai parent type, cần gửi một operation chứa cả hai nhánh trong cùng document và verify batch service, không chạy hai operation tách rời rồi so sánh tổng số lời gọi.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy DataLoader khi inject | Key/value generic type không khớp loader đã đăng ký | Kiểm tra `forTypePair` và generic của tham số controller |
| Nhiều loader cùng kiểu gây mơ hồ | Đăng ký nhiều loader cùng key/value type nhưng resolver không phân biệt | Dùng tên loader và lấy bằng `DataFetchingEnvironment` |
| Batch vẫn chạy riêng cho từng field | Mỗi field có loader riêng hoặc resolver truy vấn trực tiếp | Dùng chung một loader theo key/value type trong cùng execution |
| Dùng `@BatchMapping` nhưng muốn gọi từ root resolver | Annotation gắn với một field cụ thể | Đăng ký loader tường minh qua `BatchLoaderRegistry` |
| Kết quả bị ghép sai object | BatchLoader trả sai thứ tự hoặc Map dùng key không ổn định | Dùng mapped loader hoặc key immutable có equality đúng |
| Cache trả dữ liệu cũ sau mutation | Loader đã cache key trước khi cập nhật | Inject DataLoader và `clear`/`prime` đúng key |
| Rò dữ liệu giữa tenant | Cache/key không phản ánh security scope hoặc loader bị chia sẻ | Giới hạn registry theo request và áp dụng tenant filter |
| Query vẫn tạo quá nhiều truy vấn | Batch size, dispatch level hoặc resolver khác chưa dùng loader | Đo batch calls và kiểm tra từng field path |

## 15. Cách quyết định

Hãy bắt đầu từ hình dạng của use case. Nếu có một field lồng nhau, source object là key tự nhiên và chỉ cần gom các source object của field đó, chọn `@BatchMapping`. Nếu resolver cần gọi theo ID/key, nếu nhiều field hoặc parent type cần dùng chung dữ liệu, hoặc nếu cần điều khiển DataLoader/cache/context/options rõ ràng, chọn `BatchLoaderRegistry`.

Trong Spring for GraphQL, `BatchLoaderRegistry` là nơi đăng ký loader, còn `DataLoaderRegistry` chứa các loader instance cho execution hiện tại. `@BatchMapping` vẫn dùng DataLoader bên dưới và là lựa chọn gọn cho quan hệ field đơn giản. Chọn đúng mức trừu tượng giúp tránh N+1 mà vẫn giữ code dễ đọc, dễ kiểm thử và an toàn về cache theo request.
