# LocalGraphQlContext trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích local context trong quá trình thực thi GraphQL và lý do cần truyền dữ liệu theo nhánh field.
- Phân biệt **GraphQLContext** dùng chung cho execution với local context của một field và các field con.
- Dùng **DataFetcherResult.localContext(...)** để truyền dữ liệu từ resolver cha xuống resolver con.
- Đọc giá trị local context bằng **@LocalContextValue** trong annotated controller.
- Phân biệt source object, GraphQL context và local context.
- Chọn dữ liệu phù hợp để đưa vào local context, chẳng hạn policy, tenant scope hoặc metadata đã tính trước.
- Hiểu phạm vi kế thừa, ghi đè và giới hạn của local context trong selection tree.
- Tránh dùng local context như session, cache toàn cục hoặc cơ chế authorization độc lập.
- Kiểm thử việc truyền context qua nested field bằng **GraphQlTester**.

## 1. Local context giải quyết vấn đề gì?

Một GraphQL operation có thể resolve một object cha trước, sau đó resolve nhiều field con của object đó. Trong một số trường hợp, resolver cha đã tính được metadata mà các resolver con cần dùng.

Ví dụ, khi tải một cuốn sách, resolver có thể xác định tenant chứa sách, người dùng có thể xem ghi chú nội bộ hay không, locale dùng để định dạng dữ liệu hoặc policy đã được tính từ dữ liệu và quyền hiện tại.

Nếu mỗi nested resolver tự tính lại metadata này, ứng dụng có thể lặp công việc hoặc gọi lại service. Nếu lưu nó vào field của controller singleton, request đồng thời có thể ghi đè state của nhau.

Local context cung cấp một kênh truyền dữ liệu nội bộ từ field cha tới các field con trong nhánh thực thi tương ứng. Dữ liệu này không trở thành field trong GraphQL response và không cần được client gửi lại.

Ví dụ operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
        internalNotes
        author {
            id
            name
        }
    }
}
~~~

Resolver Query.book có thể tạo metadata một lần. Các resolver Book.internalNotes, Book.author hoặc field con sâu hơn có thể nhận metadata đó qua local context.

## 2. Phân biệt GraphQLContext và local context

Spring for GraphQL làm việc với hai loại context có phạm vi khác nhau.

| Đặc điểm | GraphQLContext | Local context |
| --- | --- | --- |
| Phạm vi | Toàn bộ GraphQL execution | Một field và các field con trong nhánh của nó |
| Nguồn tạo | Request, interceptor hoặc execution input | Kết quả do DataFetcher của field cha trả về |
| API GraphQL Java | DataFetchingEnvironment.getGraphQlContext() | DataFetchingEnvironment.getLocalContext() |
| Binding trong annotated controller | @ContextValue | @LocalContextValue |
| Mục đích | Thông tin chung của request như principal, tenant, locale | Metadata riêng của nhánh field như policy hoặc dữ liệu đã tính trước |
| Quan hệ giữa các nhánh | Có thể được các resolver trong cùng execution truy cập | Không tự động chia sẻ sang nhánh sibling hoặc root field khác |

GraphQLContext phù hợp với dữ liệu chung cho operation, ví dụ tenant và principal được xác định từ request. Local context phù hợp với dữ liệu chỉ có ý nghĩa khi resolve một object cụ thể và các field con của object đó.

Ví dụ:

- tenantId được xác định từ thông tin xác thực của request: thường thuộc GraphQLContext.
- canReadInternalNotes được tính cho một cuốn sách cụ thể: có thể thuộc local context của Book.
- authorDisplayPolicy chỉ áp dụng cho nhánh Book.author: có thể được truyền tiếp bằng local context ở nhánh đó.

Không nên đặt mọi dữ liệu vào cùng một context. Hãy chọn phạm vi nhỏ nhất đủ đáp ứng nhu cầu của resolver.

## 3. Source object không phải local context

Nested resolver thường nhận source object là object cha đang được resolve. Ví dụ:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Tham số book là source object. Nó chứa dữ liệu của cuốn sách và là giá trị mà field Book.author đang được resolve.

Local context là một kênh bổ sung. Nó có thể chứa metadata không thuộc domain object và không cần xuất hiện trong GraphQL schema.

Có thể phân biệt:

- **Source object:** object cha mà field con đang đọc hoặc dùng để tính kết quả.
- **GraphQLContext:** dữ liệu chung của execution.
- **Local context:** dữ liệu nội bộ được truyền từ field cha xuống field con.

Không cần nhét metadata tạm thời vào entity hoặc DTO chỉ để truyền cho một resolver. Nếu dữ liệu chỉ có ý nghĩa trong một nhánh selection tree, local context có thể phù hợp hơn.

## 4. Truyền local context bằng DataFetcherResult

GraphQL Java cung cấp DataFetcherResult để DataFetcher trả về dữ liệu cùng metadata thực thi. Trong Spring for GraphQL, annotated controller có thể trả về DataFetcherResult<T>.

Phần data chứa giá trị của field GraphQL. Phần localContext cung cấp object context cho các field con của giá trị đó.

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}

type Query {
    book(id: ID!): Book
}
~~~

Định nghĩa metadata dành cho field con:

~~~java
public record BookFieldPolicy(
        boolean canReadInternalNotes,
        String locale) {
}
~~~

Resolver cha:

~~~java
import graphql.execution.DataFetcherResult;
import java.util.Map;
import java.util.UUID;

@Controller
class BookQueryController {

    private final BookService bookService;
    private final BookPolicyService policyService;

    BookQueryController(
            BookService bookService,
            BookPolicyService policyService) {
        this.bookService = bookService;
        this.policyService = policyService;
    }

    @QueryMapping
    public DataFetcherResult<Book> book(@Argument("id") UUID id) {
        Book book = bookService.findById(id);
        BookFieldPolicy policy = policyService.policyFor(book);

        return DataFetcherResult.<Book>newResult()
                .data(book)
                .localContext(Map.of("bookPolicy", policy))
                .build();
    }
}
~~~

Khi GraphQL resolve Query.book, response data vẫn là object Book. Map được truyền vào local context chỉ dành cho quá trình resolve các field con.

Local context không được serialize thành một field bổ sung trong response. Client chỉ nhận các field đã chọn trong schema, ví dụ id, title và internalNotes.

## 5. Đọc local context bằng @LocalContextValue

Resolver con có thể nhận giá trị từ local context bằng @LocalContextValue:

~~~java
import org.springframework.graphql.data.method.annotation.LocalContextValue;

@Controller
class BookDetailsController {

    private final BookDetailsService detailsService;

    BookDetailsController(BookDetailsService detailsService) {
        this.detailsService = detailsService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    public String internalNotes(
            Book book,
            @LocalContextValue("bookPolicy") BookFieldPolicy policy) {

        if (!policy.canReadInternalNotes()) {
            return null;
        }

        return detailsService.findInternalNotes(book.getId(), policy);
    }
}
~~~

Trong ví dụ:

- Book là source object.
- @LocalContextValue("bookPolicy") lấy entry có key bookPolicy từ local context.
- BookFieldPolicy là kiểu Java của giá trị được truyền.
- Resolver dùng policy để quyết định cách lấy field internalNotes.

Schema khai báo internalNotes: String, tức field nullable. Vì vậy ví dụ có thể trả null khi người dùng không được xem field. Nếu schema khai báo field non-null, cần chọn cách biểu diễn từ chối truy cập và xử lý lỗi phù hợp với contract đó.

Local context chỉ giúp truyền policy tới resolver. Service vẫn cần bảo vệ dữ liệu nhạy cảm ở mọi đường truy cập có thể gọi tới nó; không coi việc có một giá trị boolean trong context là ranh giới bảo mật duy nhất.

## 6. Đặt tên và cấu trúc local context

Khi local context chứa nhiều giá trị, nên dùng các key ổn định và có ý nghĩa. Có thể gom metadata vào một record thay vì truyền nhiều giá trị rời rạc:

~~~java
public record BookLocalContext(
        BookFieldPolicy policy,
        String correlationId) {
}
~~~

Resolver cha:

~~~java
BookLocalContext localContext = new BookLocalContext(
        policyService.policyFor(book),
        correlationId
);

return DataFetcherResult.<Book>newResult()
        .data(book)
        .localContext(Map.of("bookContext", localContext))
        .build();
~~~

Resolver con:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @LocalContextValue("bookContext") BookLocalContext context) {

    return detailsService.findInternalNotes(
            book.getId(),
            context.policy()
    );
}
~~~

Cấu trúc record giúp nhóm các giá trị có quan hệ với nhau, giảm số key cần quản lý và làm rõ kiểu dữ liệu mà resolver mong đợi.

Một số nguyên tắc:

- Dùng key có tên cụ thể, tránh key chung như data, value hoặc context.
- Dùng record hoặc object bất biến khi có thể.
- Không lưu mutable state có thể bị nhiều resolver sửa đồng thời.
- Không đưa toàn bộ request hoặc entity graph lớn vào local context nếu chỉ cần một vài metadata.
- Không lưu token, credential hoặc dữ liệu bí mật nếu resolver không thực sự cần chúng.

## 7. Phạm vi local context trong selection tree

Local context được truyền từ field cha tới các field con của field đó. Nó có phạm vi theo cây thực thi GraphQL, không phải một biến toàn cục.

Ví dụ:

~~~graphql
query {
    book(id: "book-42") {
        title
        internalNotes
        author {
            name
            biography
        }
    }
    publicCatalog {
        title
    }
}
~~~

Nếu Query.book trả DataFetcherResult có local context:

- Book.title có thể được resolve trong nhánh book.
- Book.internalNotes có thể đọc local context của book.
- Book.author cũng nằm trong nhánh book.
- Author.name và Author.biography là field con sâu hơn của nhánh đó.
- Query.publicCatalog là nhánh root khác, không tự động nhận local context do Query.book tạo.

Điều này giúp mỗi nhánh có metadata riêng. Local context của một cuốn sách không tự động trở thành local context của một field root khác.

Có thể hình dung:

~~~mermaid
flowchart TD
    Q["Query execution"] --> B["Query.book"]
    Q --> C["Query.publicCatalog"]
    B -->|local context: bookPolicy| T["Book fields"]
    T --> N["Book.internalNotes"]
    T --> A["Book.author"]
    A --> D["Author.name"]
    A --> E["Author.biography"]
~~~

## 8. Truyền context sâu hơn và ghi đè local context

Một resolver con có thể tiếp tục trả DataFetcherResult để cung cấp local context phù hợp cho các field con của nó.

Ví dụ, Book.author cần policy riêng cho nhánh Author:

~~~java
public record AuthorFieldPolicy(boolean showBiography) {
}
~~~

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public DataFetcherResult<Author> author(
        Book book,
        @LocalContextValue("bookContext") BookLocalContext bookContext) {

    Author author = authorService.findById(book.getAuthorId());
    AuthorFieldPolicy authorPolicy =
            authorPolicyService.policyFor(author, bookContext.policy());

    return DataFetcherResult.<Author>newResult()
            .data(author)
            .localContext(Map.of("authorPolicy", authorPolicy))
            .build();
}
~~~

Resolver sâu hơn có thể đọc policy mới:

~~~java
@SchemaMapping(typeName = "Author", field = "biography")
public String biography(
        Author author,
        @LocalContextValue("authorPolicy") AuthorFieldPolicy policy) {

    if (!policy.showBiography()) {
        return null;
    }

    return author.getBiography();
}
~~~

Khi field trả về một DataFetcherResult có local context mới, context đó được dùng cho các field con của giá trị trả về. Nếu cần giữ lại dữ liệu từ context cũ, hãy kết hợp dữ liệu cần thiết vào object context mới một cách tường minh.

Đừng giả định context mới tự động hợp nhất mọi key của context cũ. Thiết kế record cho từng nhánh giúp thể hiện rõ metadata nào được truyền tiếp.

## 9. Local context và GraphQLContext trong cùng resolver

Một resolver có thể cần cả dữ liệu chung của request lẫn metadata riêng của nhánh field.

Ví dụ:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(
        Book book,
        @ContextValue("tenantId") UUID tenantId,
        @LocalContextValue("bookPolicy") BookFieldPolicy policy) {

    return detailsService.findInternalNotes(
            book.getId(),
            tenantId,
            policy
    );
}
~~~

Trong ví dụ:

- tenantId đến từ GraphQLContext, có phạm vi toàn execution.
- policy đến từ local context do field cha truyền xuống.
- book là source object của nested field.

Cách kết hợp này giúp tránh truyền dữ liệu chung của request qua từng cấp object nếu nhiều resolver đều cần nó. Đồng thời, metadata chỉ có ý nghĩa với một nhánh vẫn được giới hạn trong local context.

@ContextValue và @LocalContextValue không thay thế nhau. Chọn annotation dựa trên nơi giá trị được tạo và phạm vi cần truy cập.

## 10. Khi nào nên dùng local context?

Local context phù hợp khi một resolver cha đã có dữ liệu cần thiết cho nhiều field con, và dữ liệu đó chỉ có ý nghĩa trong nhánh tương ứng.

| Tình huống | Giá trị có thể truyền |
| --- | --- |
| Parent resolver đã xác định policy cho một object | Policy hoặc quyền hiển thị field |
| Parent resolver đã xác định locale riêng cho object | Locale hoặc quy tắc format |
| Một nhánh cần projection đã tính trước | Metadata về field được tải hoặc trạng thái projection |
| Nested resolver cần correlation metadata | Correlation ID hoặc thông tin tracing phù hợp |
| Nhiều field con dùng chung một kết quả tính toán nhẹ | Kết quả hoặc metadata đã tính trước |

Local context không phải lựa chọn phù hợp cho mọi loại state. Nếu thông tin cần thiết trên toàn execution, dùng GraphQLContext. Nếu dữ liệu là một phần thực sự của domain object và cần trả về cho client, hãy mô hình hóa thành field hoặc DTO. Nếu cần cache qua nhiều request, dùng cache ở tầng service hoặc hệ thống cache chuyên dụng.

## 11. Khi nào không nên dùng local context?

Không nên dùng local context để:

- Lưu trạng thái đăng nhập lâu dài hoặc thay thế security context.
- Chia sẻ dữ liệu giữa các GraphQL request độc lập.
- Tạo cache toàn cục hoặc cache liên request.
- Truyền dữ liệu sang root field sibling không thuộc nhánh hiện tại.
- Thay thế source object khi dữ liệu thực sự là một phần của domain model.
- Lưu một object lớn chỉ để tránh thiết kế service/API rõ ràng.
- Chuyển mutable state qua các resolver có thể thực thi đồng thời.

Local context tồn tại để hỗ trợ một execution tree. Nó không phải HTTP session, không phải request-scoped Spring bean và không phải thread-local.

## 12. Local context trong nested list

Một field cha có thể trả về danh sách object:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Nếu resolver Query.books trả về DataFetcherResult<List<Book>> có local context, context đó được truyền cho các field con của kết quả list trong nhánh books.

Điều này phù hợp khi metadata giống nhau cho toàn bộ danh sách, ví dụ locale hoặc một policy chung cho operation đó.

Nếu mỗi phần tử trong list cần metadata riêng, không nên đặt một map duy nhất ở local context của list rồi giả định nó tự thay đổi theo từng Book. Local context của kết quả list thuộc field books; nó không tự tạo một context khác nhau cho mỗi phần tử.

Với metadata riêng từng item, có thể:

- Đưa metadata thực sự thuộc item vào source DTO/wrapper.
- Resolve metadata trong field của từng item.
- Tạo một nhánh resolver riêng trả DataFetcherResult cho từng item nếu kiến trúc và runtime phù hợp.

Chọn cách biểu diễn sao cho dữ liệu gắn với đúng object và đúng phạm vi.

## 13. Null, lỗi và giá trị local context bị thiếu

Resolver chỉ nên yêu cầu một local context key khi field cha đảm bảo cung cấp key đó.

Ví dụ, nếu Book.internalNotes luôn cần bookPolicy, mọi đường resolve Book có field này phải tạo local context tương ứng. Nếu một root resolver khác cũng trả Book nhưng không cung cấp key, resolver con có thể không bind được giá trị như mong đợi.

Các cách xử lý:

- Bảo đảm mọi parent resolver tạo cùng contract local context cho type/field đó.
- Dùng một DTO/context type có cấu trúc thống nhất.
- Nếu giá trị thực sự tùy chọn, khai báo cách bind tùy chọn phù hợp và xử lý trường hợp không có giá trị.
- Viết test cho từng đường đi tạo ra cùng GraphQL type.

Không dùng giá trị mặc định rộng như false chỉ để che giấu việc parent resolver quên cung cấp context nếu điều đó làm thay đổi chính sách hiển thị hoặc quyền truy cập.

Local context cũng không loại bỏ quy tắc nullability của SDL. Nếu nested field là non-null nhưng resolver trả null vì thiếu context hoặc policy từ chối, GraphQL vẫn áp dụng null propagation theo schema. Hãy thiết kế output contract và error policy nhất quán.

## 14. Bảo mật và dữ liệu nhạy cảm

Local context có thể chứa thông tin như tenant scope hoặc policy đã tính. Vì vậy, cần xử lý nó như dữ liệu nội bộ của server.

Các nguyên tắc:

- Chỉ lấy tenant và principal từ nguồn xác thực đáng tin cậy.
- Không để client gửi local context trực tiếp qua GraphQL variables.
- Không đưa access token, refresh token hoặc credential vào local context.
- Không trả local context trong GraphQL response hoặc log toàn bộ object context.
- Dùng immutable value để tránh resolver khác sửa metadata dùng chung.
- Kiểm tra quyền tại service/data access layer đối với dữ liệu nhạy cảm.
- Không giả định có local context nghĩa là người gọi đã được authorization.

Ví dụ BookFieldPolicy có thể giúp resolver quyết định có hiển thị field hay không, nhưng service truy cập dữ liệu nội bộ vẫn cần áp dụng quy tắc quyền phù hợp. Điều này bảo vệ dữ liệu khi service được gọi từ resolver khác hoặc từ một luồng nghiệp vụ khác.

## 15. Kiểm thử local context bằng GraphQlTester

Nên kiểm thử từ parent resolver tới nested resolver bằng một GraphQL operation thật. Test cần xác minh:

1. Parent resolver trả đúng object trong data.
2. Parent resolver đính kèm local context.
3. Nested resolver nhận đúng key qua @LocalContextValue.
4. Giá trị local context ảnh hưởng kết quả field như mong đợi.
5. Local context không xuất hiện trong response.

Ví dụ test:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                internalNotes
            }
        }
        """)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42")
        .path("book.internalNotes")
        .entity(String.class)
        .isEqualTo("Internal editorial note");
~~~

Test này giả định parent resolver tạo bookPolicy cho phép đọc ghi chú và nested resolver dùng local context đó. Có thể bổ sung test policy từ chối truy cập để xác minh field nullable trả null hoặc trả lỗi theo chính sách ứng dụng.

Cũng nên có test cho:

- Parent resolver trả object bình thường mà không có local context.
- Một resolver sâu hơn trả DataFetcherResult với context mới.
- Hai root field có local context khác nhau.
- Nhiều item trong list dùng chung context của list.
- Một field con không tìm thấy key bắt buộc.
- GraphQL response không chứa key hoặc object local context.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| @LocalContextValue không nhận được giá trị | Parent resolver không trả local context hoặc key sai | Kiểm tra DataFetcherResult.localContext và tên key |
| Nested resolver nhận null | Nhánh GraphQL type được tạo từ parent resolver khác không cung cấp context | Chuẩn hóa contract của các parent resolver |
| Dùng @ContextValue nhưng không thấy local context | Đọc nhầm GraphQLContext toàn execution | Dùng @LocalContextValue cho local context |
| Dùng @LocalContextValue cho tenant chung nhưng không có giá trị | Tenant chỉ được đặt trong GraphQLContext | Dùng @ContextValue hoặc truyền tenant xuống local context có chủ đích |
| Context của nhánh này xuất hiện ở nhánh khác | Lưu state trong singleton hoặc static field | Truyền bằng DataFetcherResult theo từng nhánh |
| Resolver sâu không còn thấy key cũ | Resolver cha ở cấp giữa trả local context mới mà không giữ key cần thiết | Kết hợp metadata cần truyền tiếp vào context mới |
| Local context bị thay đổi ngoài dự kiến | Dùng Map/object mutable chung cho nhiều resolver | Dùng record và collection bất biến |
| Local context của list không khác nhau theo item | Đặt metadata per-item ở cấp kết quả list | Đưa metadata vào source item hoặc resolver từng item |
| Dữ liệu nhạy cảm vẫn bị truy cập qua service khác | Chỉ dựa vào policy trong local context | Kiểm tra authorization ở service/data access layer |
| Test pass nhưng production thiếu context | Chỉ test một đường parent resolver | Test mọi resolver có thể trả cùng GraphQL type |

## 17. Quy trình thiết kế LocalGraphQlContext

Khi cần truyền metadata từ resolver cha xuống field con, hãy thực hiện theo trình tự:

1. **Xác định nơi tạo dữ liệu.** Giá trị được tạo từ request chung hay từ một object cụ thể?
2. **Chọn đúng loại context.** Dùng GraphQLContext cho toàn execution; dùng local context cho một nhánh field.
3. **Xác định source object.** Không nhầm source với metadata nội bộ.
4. **Định nghĩa kiểu context.** Ưu tiên record hoặc object bất biến có tên rõ ràng.
5. **Trả DataFetcherResult.** Đặt dữ liệu GraphQL trong data và metadata trong localContext.
6. **Bind ở resolver con.** Dùng @LocalContextValue với key thống nhất.
7. **Rà soát field sâu hơn.** Nếu cần context mới, truyền rõ dữ liệu cần giữ lại.
8. **Kiểm tra mọi parent resolver.** Cùng một GraphQL type có thể được tạo từ nhiều root field.
9. **Đánh giá nullability và bảo mật.** Thiếu context không được âm thầm biến thành quyền truy cập.
10. **Kiểm thử bằng GraphQlTester.** Bao gồm nhiều nhánh, nested list và trường hợp context bị thiếu.

## 18. Tổng kết

Local context là kênh truyền dữ liệu nội bộ từ một field GraphQL tới các field con trong nhánh thực thi của field đó. Trong Spring for GraphQL, resolver cha có thể trả DataFetcherResult<T> và dùng localContext(...) để đính kèm metadata; resolver con đọc giá trị bằng @LocalContextValue.

Local context khác GraphQLContext ở phạm vi: GraphQLContext dùng chung cho execution, còn local context gắn với nhánh field. Nó cũng khác source object vì chỉ mang metadata bổ sung, không thay thế object cha. Dùng local context cho policy hoặc dữ liệu đã tính trước giúp tránh tính toán lặp và tránh đưa metadata nội bộ vào GraphQL schema. Hãy giữ context bất biến, không dùng nó làm cache liên request hay cơ chế authorization độc lập, và kiểm thử toàn bộ đường truyền từ parent resolver tới nested field bằng GraphQlTester.

