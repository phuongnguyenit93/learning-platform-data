# Test schema mapping

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao cần kiểm thử mapping giữa GraphQL schema và data fetcher.
- Dùng @GraphQlTest để kiểm thử annotated controller và @SchemaMapping.
- Kiểm tra việc bind argument, source object và nested field.
- Xác minh một nested resolver chỉ chạy khi field được chọn.
- Kiểm thử @BatchMapping với nhiều parent object.
- Kiểm tra GraphQL errors, partial data và null propagation do field resolver.
- Dùng schema mapping inspection để phát hiện mapping thiếu hoặc sai.
- Chọn giữa GraphQlTester, ExecutionGraphQlServiceTester, WebGraphQlTester và HttpGraphQlTester.

## Schema mapping là gì?

GraphQL schema mô tả API mà client có thể gọi: object type, field, argument, scalar, enum, interface và union. Schema mapping kết nối những khai báo đó với logic thực thi ở server.

Trong Spring for GraphQL, annotated controller method có thể trở thành data fetcher cho một field:

- @QueryMapping ánh xạ method tới field trong root Query.
- @MutationMapping ánh xạ method tới field trong root Mutation.
- @SubscriptionMapping ánh xạ method tới field trong root Subscription.
- @SchemaMapping ánh xạ method tới field của một object type hoặc interface.
- @BatchMapping gom việc phân giải một field cho nhiều parent object.

Một method @SchemaMapping có thể nhận parent/source object, argument, Principal hoặc DataFetchingEnvironment. Khi GraphQL thực thi query, framework tìm đúng data fetcher, bind tham số, gọi method và đưa kết quả vào response.

Kiểm thử schema mapping cần xác minh cả hai phía: operation phải hợp lệ với SDL, và field phải được nối với đúng controller method. Chỉ gọi trực tiếp Java method không chứng minh rằng GraphQL runtime đã đăng ký mapping hoặc bind source và arguments đúng.

## Vì sao nên kiểm thử qua GraphQL operation?

Giả sử schema có:

~~~graphql
type Query {
  book(id: ID!): Book!
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

Client có thể gửi:

~~~graphql
query {
  book(id: "book-101") {
    title
    author {
      name
    }
  }
}
~~~

Server phải thực hiện một chuỗi công việc:

1. Parse và validate operation với schema.
2. Gọi data fetcher cho Query.book.
3. Nhận Book làm source object của field con.
4. Gọi mapping cho Book.author nếu client chọn field đó.
5. Gọi tiếp mapping của Author.name hoặc đọc property tương ứng.
6. Ghép các giá trị thành response data.

Một unit test chỉ gọi BookController.author(book) sẽ không phát hiện được các lỗi như:

- Annotation khai báo sai typeName hoặc field.
- Field không tồn tại hoặc sai tên trong SDL.
- Tham số source không được bind như mong đợi.
- Argument có tên hoặc kiểu không khớp.
- Resolver không được đăng ký vào GraphQL runtime.
- Client không chọn nested field nên resolver không chạy.

Vì vậy, hãy gửi GraphQL document qua tester để kiểm tra mapping trong ngữ cảnh thực thi.

## Chọn tester phù hợp

Spring for GraphQL có các tester ở nhiều lớp:

| Tester | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| ExecutionGraphQlServiceTester | GraphQL execution trực tiếp qua ExecutionGraphQlService | Kiểm tra schema, resolver và data fetcher không cần web transport |
| WebGraphQlTester | WebGraphQlHandler và WebGraphQlInterceptor | Kiểm tra thêm web interceptor hoặc request context |
| HttpGraphQlTester | HTTP endpoint qua WebTestClient | Kiểm tra HTTP routing, headers, filter chain và response transport |
| WebSocketGraphQlTester | WebSocket GraphQL transport | Kiểm thử subscription qua WebSocket |

Đối với controller slice test trong Spring Boot, @GraphQlTest thường là lựa chọn thuận tiện. Annotation này cấu hình GraphQL infrastructure và cung cấp GraphQlTester mà không cần khởi động HTTP server.

Nếu chỉ muốn kiểm tra execution, có thể tạo ExecutionGraphQlServiceTester trực tiếp. Nếu mục tiêu là xác minh HTTP filter hoặc security header, cần HttpGraphQlTester; ExecutionGraphQlServiceTester không đi qua web layer.

## Chuẩn bị schema và controller

Đặt schema test hoặc schema ứng dụng dưới thư mục GraphQL resources. Cấu hình Spring Boot mặc định tìm các file .graphqls và .gqls trong classpath:graphql/**, thường là src/main/resources/graphql.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book!
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

Các model Java:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

Book chứa authorId để resolver tra cứu tác giả. Schema không công khai authorId; client chỉ truy vấn field author. Đây là tình huống phổ biến khi cấu trúc model nội bộ khác với API GraphQL.

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book source) {
        return authorService.findById(source.authorId());
    }
}
~~~

Method book xử lý root field Query.book. Method author xử lý nested field Book.author. Tham số Book source là parent object được trả về từ resolver cha.

## Kiểm thử controller bằng @GraphQlTest

Với Spring Boot 4.2, thêm các dependency kiểm thử tương ứng và để Spring Boot quản lý phiên bản:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-graphql-test'
}
~~~

spring-graphql-test cung cấp GraphQlTester và các tester theo từng lớp. spring-boot-graphql-test cung cấp slice test annotation @GraphQlTest trong Spring Boot 4.x. Với Spring Boot 3.x hoặc phiên bản cũ hơn, artifact và package của annotation có thể khác; hãy dùng dependency management và tài liệu đúng phiên bản của dự án.

Ví dụ test:

~~~java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void resolvesBookAndNestedAuthor() {
        Book book = new Book(
                "book-101",
                "Spring for GraphQL",
                "author-12");
        Author author = new Author("author-12", "Ada Nguyen");

        given(bookService.findById("book-101")).willReturn(book);
        given(authorService.findById("author-12")).willReturn(author);

        GraphQlTester.Response response = graphQlTester.document("""
                query BookDetails($id: ID!) {
                    book(id: $id) {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
                .variable("id", "book-101")
                .execute();

        response.path("book.id")
                .entity(String.class)
                .isEqualTo("book-101");

        response.path("book.author.name")
                .entity(String.class)
                .isEqualTo("Ada Nguyen");

        response.errors().verify();

        verify(bookService).findById("book-101");
        verify(authorService).findById("author-12");
    }
}
~~~

@GraphQlTest chỉ quét các thành phần thuộc GraphQL slice như @Controller, @ControllerAdvice, RuntimeWiringConfigurer, converter và DataFetcherExceptionResolver. Các service thông thường không tự động được tạo trong slice. Dùng @MockitoBean để thay thế collaborator, hoặc @Import nếu cần đưa một cấu hình hỗ trợ cụ thể vào test.

## Kiểm tra source object và field argument

Schema mapping thường cần cả parent object lẫn argument của field con. Ví dụ:

~~~graphql
type Book {
  recommendations(first: Int!): [Book!]!
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "recommendations")
public List<Book> recommendations(
        Book source,
        @Argument("first") int first) {

    return recommendationService.findForBook(source.id(), first);
}
~~~

Test operation:

~~~graphql
query {
  book(id: "book-101") {
    recommendations(first: 3) {
      id
      title
    }
  }
}
~~~

Trong test, mock service để trả về ba sách và xác minh service nhận đúng cả source ID lẫn argument first:

~~~java
given(recommendationService.findForBook("book-101", 3))
        .willReturn(recommendedBooks);

GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-101") {
                recommendations(first: 3) {
                    id
                    title
                }
            }
        }
        """)
        .execute();

response.path("book.recommendations")
        .entityList(Book.class)
        .hasSize(3);

verify(recommendationService).findForBook("book-101", 3);
~~~

Test này xác minh framework đã bind parent Book vào source parameter và bind first vào @Argument. Nếu tên argument trong annotation không khớp schema, operation có thể lỗi hoặc tham số nhận giá trị không như mong đợi.

## Kiểm tra resolver chỉ chạy khi field được chọn

GraphQL chỉ phân giải field có trong selection set. Nếu client chỉ yêu cầu title, resolver Book.author không cần chạy.

Ví dụ:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotResolveAuthorWhenFieldIsNotSelected() {
    Book book = new Book("book-101", "Spring for GraphQL", "author-12");
    given(bookService.findById("book-101")).willReturn(book);

    graphQlTester.document("""
            query {
                book(id: "book-101") {
                    title
                }
            }
            """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");

    verify(bookService).findById("book-101");
    verifyNoInteractions(authorService);
}
~~~

Để assertion verifyNoInteractions chạy, import static org.mockito.Mockito.verifyNoInteractions. Kiểm tra này hữu ích khi nested resolver truy cập database hoặc dịch vụ ngoài; nó xác minh server không thực hiện công việc mà client không yêu cầu.

Không nên dùng interaction assertion quá mức. Nếu implementation được phép đổi cách tải dữ liệu nhưng response contract không đổi, hãy ưu tiên assert kết quả. Chỉ xác minh số lần gọi collaborator khi đó là yêu cầu hiệu năng hoặc batching cần được bảo vệ.

## Kiểm thử @BatchMapping

@BatchMapping ánh xạ một field cho danh sách parent object. Thay vì gọi service riêng cho từng Book, resolver nhận List<Book> và tải Author theo batch:

Trong schema dành cho biến thể batch, bổ sung field root sau:

~~~graphql
extend type Query {
  books: [Book!]!
}
~~~

~~~java
@Controller
public class BookBatchController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookBatchController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsForBooks(books);
    }
}
~~~

Test nên gửi query có nhiều parent object và chọn nested field author:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

Thiết lập fixture:

Đặt BookBatchController trong test slice riêng bằng @GraphQlTest(BookBatchController.class), rồi dùng @MockitoBean cho BookService và AuthorService. Không đưa đồng thời BookController và BookBatchController vào cùng slice nếu cả hai cùng đăng ký một mapping Book.author.

~~~java
Book firstBook = new Book("book-1", "GraphQL Basics", "author-1");
Book secondBook = new Book("book-2", "Spring APIs", "author-2");
Author firstAuthor = new Author("author-1", "An");
Author secondAuthor = new Author("author-2", "Binh");

given(bookService.findAll()).willReturn(List.of(firstBook, secondBook));
given(authorService.findAuthorsForBooks(List.of(firstBook, secondBook)))
        .willReturn(Map.of(
                firstBook, firstAuthor,
                secondBook, secondAuthor));
~~~

Sau đó assert cả hai nhánh:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            books {
                id
                author {
                    name
                }
            }
        }
        """)
        .execute();

response.path("books[0].author.name")
        .entity(String.class)
        .isEqualTo("An");

response.path("books[1].author.name")
        .entity(String.class)
        .isEqualTo("Binh");

response.errors().verify();
verify(authorService).findAuthorsForBooks(List.of(firstBook, secondBook));
~~~

Test này kiểm tra mapping trả đúng tác giả cho từng source object và service batch được gọi với tập parent cần thiết. Nếu dùng Map<Book, Author>, Book cần equality/hashCode ổn định để map tìm đúng key. Nếu resolver trả List, thứ tự phần tử phải tương ứng với thứ tự parent theo contract của batch mapping.

Không nên chỉ kiểm tra tổng số lần gọi service mà bỏ qua kết quả từng parent. Một batch có thể chỉ chạy một lần nhưng ghép nhầm Author với Book; assertion theo từng path mới phát hiện được lỗi đó.

## Kiểm tra GraphQL error từ schema mapping

Nested resolver có thể ném exception. GraphQL ghi nhận lỗi theo path của field và có thể vẫn trả partial data nếu field nullable.

Ví dụ schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Nếu AuthorService không tìm thấy tác giả và resolver ném exception, test có thể kiểm tra title vẫn có dữ liệu trong khi author là null:

~~~java
given(bookService.findById("book-101"))
        .willReturn(new Book("book-101", "Spring for GraphQL", "missing-author"));
given(authorService.findById("missing-author"))
        .willThrow(new AuthorNotFoundException("missing-author"));

GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-101") {
                title
                author {
                    name
                }
            }
        }
        """)
        .execute();

response.path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getPath())
            .containsExactly("book", "author");
});
~~~

Nếu schema khai báo author: Author!, lỗi có thể lan truyền lên Book hoặc xa hơn theo quy tắc null propagation. Test phải phản ánh nullability thực tế trong SDL.

Nếu ứng dụng có DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler, kiểm tra error code trong extensions để bảo vệ error contract. Không chỉ kiểm tra message tự do vì message có thể được thay đổi hoặc bản địa hóa.

## Schema mapping inspection

Một số lỗi mapping không nhất thiết làm ứng dụng khởi động thất bại. Ví dụ schema có field không được đăng ký data fetcher và cũng không có property tương ứng trên source object; field có thể trả null mà không có exception rõ ràng.

Spring for GraphQL cung cấp schema mapping inspection để rà soát mapping lúc khởi động. Inspection có thể phát hiện:

- Schema field không có data fetcher hoặc property tương ứng.
- Data fetcher đăng ký vào field không tồn tại trong schema.
- Argument trong controller method không khớp argument của schema field.
- Một số khác biệt nullability giữa schema và Java type khi thông tin kiểu có thể xác định.

Có thể cấu hình qua GraphQlSource.Builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;

@Configuration
public class GraphQlInspectionConfiguration {

    private static final Logger logger =
            LoggerFactory.getLogger(GraphQlInspectionConfiguration.class);

    @Bean
    GraphQlSourceBuilderCustomizer schemaMappingInspection() {
        return builder -> builder.inspectSchemaMappings(
                report -> logger.info("GraphQL schema mapping inspection:\n{}", report));
    }
}
~~~

Inspection report là chẩn đoán bổ sung. Nó không thay thế GraphQL integration test: inspection không thể xác minh dữ liệu runtime, quyền truy cập, nhánh nghiệp vụ hoặc kết quả repository. Ngược lại, test chỉ cover operation được gửi; inspection giúp phát hiện những field chưa được test gọi tới.

Khi có interface hoặc union, một số mapping có thể không đủ thông tin Java type để inspection kết luận. Hãy đọc cả phần skipped types trong report và bổ sung type mapping nếu cần.

## Kiểm thử bằng ExecutionGraphQlServiceTester

Nếu không dùng Spring Boot slice test, có thể tạo tester trực tiếp từ ExecutionGraphQlService:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);
~~~

Tester này chạy operation ở server execution layer mà không cần HTTP hoặc WebSocket transport. Nó phù hợp với ứng dụng tự cấu hình GraphQlSource và ExecutionGraphQlService, hoặc khi muốn test một cấu hình execution cụ thể.

Nếu test cần xác minh WebGraphQlInterceptor, dùng WebGraphQlTester với WebGraphQlHandler. Nếu cần xác minh HTTP request thực sự đi qua server, dùng HttpGraphQlTester. Không chọn ExecutionGraphQlServiceTester rồi kết luận rằng HTTP filter hoặc authentication header đã hoạt động.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Controller method không được gọi | Sai annotation, typeName hoặc field name | So khớp annotation với schema và query |
| Query trả null dù controller có method | Mapping không được đăng ký hoặc method signature không phù hợp | Kiểm tra @Controller, GraphQlSource và test qua GraphQL operation |
| Nested resolver không chạy | Client không chọn nested field | Kiểm tra selection set |
| Resolver nhận sai source object | Method nhận nhầm kiểu parent hoặc mapping sai typeName | Kiểm tra source parameter và GraphQL parent type |
| Argument nhận null hoặc giá trị mặc định | Tên argument không khớp hoặc schema cho phép null | Dùng @Argument với tên rõ ràng và kiểm tra SDL |
| Test pass dù mapping sai | Test gọi trực tiếp Java method | Gửi document qua GraphQlTester |
| @GraphQlTest không tìm thấy service | Slice test không quét component thông thường | Dùng @MockitoBean hoặc @Import |
| Batch mapping trả sai parent-child pair | Map key hoặc thứ tự List không đúng | Assert nested value cho từng parent |
| Field null không có lỗi | Không có data fetcher và không có property tương ứng | Bổ sung resolver và bật schema mapping inspection |
| Field con lỗi làm mất cả object cha | Field hoặc parent được khai báo non-null | Kiểm tra nullability và contract partial data |
| Test không kiểm tra được HTTP authentication | Dùng tester không đi qua transport | Dùng HttpGraphQlTester với WebTestClient |

## Thực hành tổng hợp

Xây dựng test suite cho schema thư viện:

1. Tạo schema có Query.book, Book.author và Book.recommendations(first: Int!).
2. Viết BookController với @QueryMapping và hai @SchemaMapping.
3. Dùng @GraphQlTest để tạo slice test và inject GraphQlTester.
4. Mock BookService, AuthorService và RecommendationService bằng @MockitoBean.
5. Gửi query lấy Book.author.name và xác minh parent object được truyền đúng.
6. Gửi query có recommendations(first: 3) và xác minh field argument được bind đúng.
7. Gửi query chỉ chọn title và xác minh resolver author không được gọi.
8. Tạo một biến thể dùng @BatchMapping để tải tác giả cho nhiều sách.
9. Xác minh kết quả nested field theo từng parent object, không chỉ kiểm tra số lần gọi batch.
10. Tạo trường hợp resolver ném exception và kiểm tra error path, partial data, null propagation.
11. Bật schema mapping inspection để rà soát field và argument chưa được ánh xạ.
12. Bổ sung WebGraphQlTester hoặc HttpGraphQlTester nếu cần kiểm tra interceptor hoặc HTTP transport.

Sau khi hoàn thành, hãy giải thích vì sao cần gửi GraphQL operation thay vì gọi trực tiếp controller method, cách GraphQL truyền source object xuống nested resolver và vì sao batch mapping cần kiểm tra kết quả theo từng parent.

## Ghi nhớ

Schema mapping nối field trong GraphQL SDL với data fetcher thực thi trên server. Dùng @GraphQlTest và GraphQlTester để kiểm tra operation qua runtime, bao gồm root mapping, nested mapping, source object và argument binding. Với @BatchMapping, xác minh mỗi parent nhận đúng kết quả tương ứng. Kiểm tra cả errors, partial data và null propagation khi resolver thất bại. Schema mapping inspection bổ sung khả năng phát hiện field hoặc argument chưa được ánh xạ ngay từ lúc khởi động. Chọn ExecutionGraphQlServiceTester cho execution layer, WebGraphQlTester cho web handler/interceptor và HttpGraphQlTester cho HTTP transport.

## Tài liệu tham khảo

- [Spring Boot – Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL – Annotated Controllers and Schema Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL – Schema Mapping Inspection](https://docs.spring.io/spring-graphql/reference/request-execution.html)
