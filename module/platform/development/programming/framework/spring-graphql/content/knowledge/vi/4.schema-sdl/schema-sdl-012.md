# Tổ chức nhiều file schema trong Spring for GraphQL

Một GraphQL schema có thể được chia thành nhiều file SDL để nhóm các type và field theo chức năng. Spring for GraphQL cùng Spring Boot hỗ trợ đọc nhiều schema resource và kết hợp chúng thành một `GraphQLSchema` duy nhất trước khi phục vụ request.

Việc chia file giúp schema lớn dễ đọc, dễ tìm và dễ giao quyền sở hữu theo domain. Tuy nhiên, GraphQL vẫn kiểm tra toàn bộ schema như một hợp đồng thống nhất: tên type phải duy nhất, các phần mở rộng phải hợp lệ và mọi tham chiếu type phải được định nghĩa trong schema cuối cùng.

## 1. Vì sao nên chia schema thành nhiều file?

Ở giai đoạn đầu, một ứng dụng có thể chỉ cần một file `schema.graphqls`. Khi API phát triển, file này sẽ chứa nhiều root field, object type, input type, enum và directive. Một file quá lớn gây khó khăn khi tìm định nghĩa, review thay đổi và xác định phần nào thuộc domain nào.

Ví dụ, một ứng dụng quản lý thư viện có thể chia schema theo nhóm:

- `common`: scalar, enum và directive dùng chung.
- `book`: type, input và operation liên quan đến sách.
- `author`: type, input và operation liên quan đến tác giả.
- `member`: type và operation liên quan đến thành viên.
- `schema`: các root type hoặc định nghĩa chung của API.

Các file này không tạo thành nhiều GraphQL endpoint hay nhiều schema độc lập. Chúng được kết hợp thành một schema, nên client vẫn gửi operation tới một endpoint GraphQL và có thể chọn field thuộc nhiều domain trong cùng một query.

## 2. Cách GraphQL kết hợp các định nghĩa SDL

GraphQL SDL hỗ trợ hai cách tổ chức định nghĩa:

1. **Type definition** khai báo một type mới, ví dụ `type Book`, `input BookInput` hoặc `enum BookStatus`.
2. **Type extension** mở rộng một type đã được khai báo, ví dụ `extend type Query` thêm root field từ một domain khác.

Khi schema được chia thành nhiều file, mỗi type thông thường chỉ nên có một định nghĩa gốc. Các file domain bổ sung field cho root type hoặc type dùng chung bằng cú pháp `extend`.

### 2.1. Khai báo root type một lần

File `graphql/schema.graphqls` có thể giữ các field nền tảng của API:

~~~graphql
type Query {
    apiVersion: String!
}
~~~

Đây là định nghĩa gốc của `Query`. Các file khác có thể thêm field bằng `extend type Query`.

Nếu API dùng tên root type mặc định `Query`, `Mutation` và `Subscription`, GraphQL không bắt buộc phải có khối `schema { ... }`. Nếu cần đổi tên root type, khai báo schema definition một lần trong file nền tảng:

~~~graphql
schema {
    query: RootQuery
    mutation: RootMutation
}

type RootQuery {
    apiVersion: String!
}

type RootMutation {
    noop: Boolean!
}
~~~

Không lặp lại nhiều `schema { ... }` trong các file domain. Các domain chỉ mở rộng đúng root type đã được chỉ định, ví dụ `extend type RootQuery`.

### 2.2. Dùng type extension để thêm field

Giả sử domain sách có type `Book` và hai query. File `graphql/book/book.graphqls` khai báo:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}

extend type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

Domain tác giả có thể khai báo type riêng và bổ sung query vào cùng root type trong file `graphql/author/author.graphqls`:

~~~graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

extend type Query {
    author(id: ID!): Author
    authors: [Author!]!
}
~~~

`Book` tham chiếu đến `Author` và `Author` tham chiếu ngược lại `Book`. Điều này hợp lệ vì GraphQL kiểm tra các định nghĩa trên schema tổng hợp; không yêu cầu một type phải được khai báo trong cùng file với type đang tham chiếu nó.

Sau khi ghép các file, root type `Query` có các field `apiVersion`, `book`, `books`, `author` và `authors`. Client có thể truy vấn dữ liệu từ hai domain trong cùng một operation:

~~~graphql
query LibraryOverview {
    books {
        id
        title
        author {
            id
            name
        }
    }
    authors {
        id
        name
    }
}
~~~

Các resolver tương ứng vẫn được triển khai bằng controller và service của Spring for GraphQL. Việc tách file SDL không làm thay đổi cách ánh xạ `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping`.

## 3. Cấu trúc thư mục schema gợi ý

Spring Boot mặc định tìm schema trong `classpath:graphql/**/` với phần mở rộng `.graphqls` và `.gqls`. Có thể tận dụng thư mục con để phân nhóm file theo domain:

~~~text
src/main/resources/
└── graphql/
    ├── schema.graphqls
    ├── common/
    │   ├── scalars.graphqls
    │   ├── enums.graphqls
    │   └── directives.graphqls
    ├── book/
    │   ├── book.graphqls
    │   ├── book-input.graphqls
    │   └── book-mutation.graphqls
    ├── author/
    │   ├── author.graphqls
    │   └── author-query.graphqls
    └── member/
        ├── member.graphqls
        └── member-mutation.graphqls
~~~

Đây là cách tổ chức tham khảo, không phải cấu trúc bắt buộc. Với schema nhỏ, vài file theo domain là đủ. Không nên tạo quá nhiều file chỉ để tách từng type đơn lẻ; mục tiêu là giúp người phát triển tìm được một phần hợp đồng API có liên quan trong cùng khu vực.

### 3.1. Chia file theo domain thay vì chỉ theo loại type

Có hai cách thường gặp:

| Cách chia | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Theo loại khai báo | `queries.graphqls`, `mutations.graphqls`, `types.graphqls` | Dễ tìm theo cú pháp GraphQL lúc schema còn nhỏ, nhưng một domain bị phân tán ở nhiều file |
| Theo domain | `book.graphqls`, `author.graphqls`, `member.graphqls` | Giữ type, input và field liên quan gần nhau; phù hợp khi API phát triển theo nghiệp vụ |

Với ứng dụng có nhiều domain, cách chia theo domain thường thuận tiện hơn. Có thể giữ một vài file dùng chung cho scalar, directive, enum thật sự dùng ở nhiều nơi.

## 4. Chia root field giữa các domain

`Query`, `Mutation` và `Subscription` là các root type được nhiều domain cùng đóng góp. Hãy khai báo type gốc một lần, sau đó mở rộng nó trong các file domain.

Ví dụ file `graphql/schema.graphqls`:

~~~graphql
type Query {
    apiVersion: String!
}

type Mutation {
    healthCheck: Boolean!
}
~~~

File `graphql/book/book-mutation.graphqls`:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}

extend type Mutation {
    createBook(input: CreateBookInput!): Book!
    deleteBook(id: ID!): Boolean!
}
~~~

File `graphql/member/member-mutation.graphqls`:

~~~graphql
input RegisterMemberInput {
    email: String!
    displayName: String!
}

extend type Mutation {
    registerMember(input: RegisterMemberInput!): Member!
}
~~~

Các file domain có thể mở rộng cùng `Mutation` mà không phải sửa file root mỗi khi thêm nghiệp vụ. Cần bảo đảm mỗi field name trong cùng một object type là duy nhất. Nếu hai domain cùng khai báo `create` mà không có quy ước tên rõ ràng, schema sẽ xung đột hoặc API khó hiểu.

Tương tự, có thể dùng `extend type Subscription` để chia các luồng sự kiện theo domain:

~~~graphql
extend type Subscription {
    bookCreated: Book!
}
~~~

Đoạn mở rộng này giả định `type Subscription` đã được khai báo gốc trong schema nền tảng. Các field subscription vẫn cần resolver trả về publisher và transport hỗ trợ subscription. Type extension chỉ hợp nhất schema, không tự tạo nguồn sự kiện.

## 5. Dùng chung scalar, enum, input và directive

Các định nghĩa dùng chung nên được đặt trong khu vực `common` và khai báo đúng một lần.

### 5.1. Custom scalar

File `graphql/common/scalars.graphqls`:

~~~graphql
scalar DateTime
scalar BigDecimal
~~~

Việc khai báo `scalar DateTime` trong SDL chỉ tạo tên kiểu. Ứng dụng vẫn phải đăng ký implementation tương ứng trong runtime wiring, ví dụ qua `RuntimeWiringConfigurer` hoặc `GraphQlSourceBuilderCustomizer`:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiring -> wiring
            .scalar(ExtendedScalars.DateTime)
            .scalar(ExtendedScalars.GraphQLBigDecimal);
}
~~~

Ví dụ trên minh họa cách đăng ký scalar có sẵn trong thư viện Extended Scalars; tên scalar trong SDL và implementation phải tương thích. Nếu tự định nghĩa scalar `Money`, cần khai báo `scalar Money` trong SDL và cung cấp `GraphQLScalarType` tương ứng, cùng quy tắc parse, serialize và validation.

### 5.2. Enum và input type

File `graphql/common/enums.graphqls`:

~~~graphql
enum SortDirection {
    ASC
    DESC
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}
~~~

Domain sách có thể tham chiếu `BookStatus` trong type hoặc input:

~~~graphql
input BookFilterInput {
    status: BookStatus
    keyword: String
}
~~~

Định nghĩa enum dùng chung giúp các domain có cùng cách biểu diễn trạng thái. Tuy nhiên, chỉ nên chia sẻ enum khi ý nghĩa nghiệp vụ thật sự giống nhau; hai giá trị có tên giống nhau nhưng quy tắc khác nhau nên được định nghĩa riêng.

### 5.3. Directive

File `graphql/common/directives.graphqls` có thể khai báo directive tùy chỉnh:

~~~graphql
directive @upperCase on FIELD_DEFINITION
~~~

Domain sử dụng directive:

~~~graphql
type MemberProfile {
    id: ID!
    displayName: String! @upperCase
}
~~~

Directive declaration chỉ mô tả directive hợp lệ ở vị trí nào. Muốn directive thay đổi hành vi thực thi, ứng dụng cần triển khai directive wiring hoặc cơ chế tương ứng trong GraphQL Java. Chia declaration sang file riêng không tự đăng ký hành vi runtime.

## 6. Cấu hình Spring Boot để nạp nhiều file

Với `spring-boot-starter-graphql`, không cần tự đọc từng file nếu các resource nằm trong vị trí mặc định. Starter tự tìm schema resources theo cấu hình `spring.graphql.schema.locations` và phần mở rộng được hỗ trợ.

Cấu hình mặc định thường tương ứng với:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
~~~

Pattern `classpath:graphql/**/` cho phép tìm schema trong thư mục `graphql` và các thư mục con. Vì vậy các file trong `graphql/book`, `graphql/author` và `graphql/common` đều có thể được nạp.

Nếu schema đặt ở vị trí khác, có thể đổi locations:

~~~yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
        - classpath:shared-graphql/**/
~~~

Khi thay đổi locations, hãy chắc chắn các resource mong muốn đều được bao gồm. Cấu hình một location tùy chỉnh có thể khiến ứng dụng bỏ sót file vẫn nằm trong thư mục mặc định nếu bạn không khai báo cả hai.

### 6.1. Phần mở rộng file

Spring Boot hỗ trợ các phần mở rộng schema `.graphqls` và `.gqls` theo cấu hình mặc định. Nên dùng thống nhất một phần mở rộng trong cùng project để người phát triển dễ nhận biết file SDL. Nếu thay đổi `spring.graphql.schema.file-extensions`, hãy xác nhận cấu hình mới bao gồm tất cả loại file đang sử dụng.

### 6.2. Đóng gói schema trong JAR

Schema nằm trong `src/main/resources` sẽ được đóng gói vào classpath của ứng dụng. Khi chạy từ IDE, file có thể được đọc từ thư mục resources; khi chạy JAR, resource được đọc từ bên trong JAR. Tránh dùng đường dẫn file hệ điều hành như `C:/project/schema.graphqls`, vì đường dẫn đó không còn đúng khi triển khai ở môi trường khác.

## 7. Nạp schema resource thủ công

Nếu không dùng Spring Boot auto-configuration hoặc muốn tự tạo `GraphQlSource`, Spring for GraphQL cung cấp `GraphQlSource.schemaResourceBuilder()` để chỉ định nhiều resource:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class ManualGraphQlSourceConfiguration {

    @Bean
    GraphQlSource graphQlSource(RuntimeWiringConfigurer runtimeWiringConfigurer) {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls"),
                        new ClassPathResource("graphql/common/scalars.graphqls"),
                        new ClassPathResource("graphql/book/book.graphqls"),
                        new ClassPathResource("graphql/author/author.graphqls")
                )
                .configureRuntimeWiring(runtimeWiringConfigurer::configure)
                .build();
    }
}
~~~

Đây là ví dụ cấu hình thủ công: ứng dụng phải cung cấp đầy đủ resource và runtime wiring cần thiết. Khi tự khai báo `GraphQlSource` bean trong ứng dụng Spring Boot, auto-configuration tạo source mặc định có thể lùi lại do điều kiện thiếu bean. Khi đó, các cấu hình mà auto-configuration trước đây cung cấp phải được chuyển sang cấu hình thủ công tương ứng.

Với ứng dụng dùng Boot starter, nên ưu tiên `spring.graphql.schema.locations` nếu chỉ cần thêm thư mục. Dùng builder thủ công khi có nhu cầu kiểm soát trực tiếp việc tạo source hoặc khi ứng dụng không sử dụng auto-configuration.

## 8. Resolver Java không phụ thuộc số lượng file SDL

Sau khi các file được hợp nhất, GraphQL engine nhìn thấy một schema thống nhất. Spring for GraphQL vẫn ánh xạ resolver theo type và field name.

Ví dụ controller cho các query của domain sách:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

Controller cho domain tác giả có thể nằm trong class riêng:

~~~java
@Controller
public class AuthorController {

    private final AuthorService authorService;

    public AuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @QueryMapping
    public Author author(@Argument String id) {
        return authorService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Author> authors() {
        return authorService.findAll();
    }
}
~~~

Tên method mặc định được dùng làm tên field nếu không chỉ định tên khác trong annotation. Nếu nhiều controller cùng ánh xạ một field hoặc hai resolver có cùng type và field mapping, cần xử lý xung đột rõ ràng. Việc tách SDL theo file không tự động cô lập resolver hoặc tạo namespace cho field.

Khi một object type có field liên kết đến domain khác, `@SchemaMapping` hoặc `@BatchMapping` vẫn hoạt động trên schema tổng hợp. Ví dụ `Book.author` có thể được resolve bởi một method trong `BookController`, dù `Author` được định nghĩa ở file SDL khác.

## 9. Quy tắc quan trọng khi chia schema

### 9.1. Không khai báo trùng type

Không nên định nghĩa `type Query` trong nhiều file như thể mỗi file là một schema độc lập. Cách này tạo xung đột định nghĩa. Hãy khai báo một type gốc và mở rộng ở file domain:

~~~graphql
# schema.graphqls
type Query {
    apiVersion: String!
}

# book.graphqls
extend type Query {
    books: [Book!]!
}
~~~

Quy tắc tương tự áp dụng cho object type, input type, enum, interface và union: dùng type extension khi muốn thêm thành phần vào một định nghĩa đã có và bảo đảm extension hợp lệ theo phiên bản GraphQL Java đang sử dụng.

### 9.2. Type extension cần type gốc

`extend type Query` không tạo type `Query` từ con số không. Nếu không có file nào khai báo `type Query`, schema validation sẽ thất bại. Hãy giữ định nghĩa root type trong một file nền tảng hoặc bảo đảm có một định nghĩa gốc ở vị trí khác.

### 9.3. Khai báo scalar, directive và schema definition một lần

Các khai báo như `scalar DateTime`, `directive @upperCase ...` và `schema { ... }` nên có một nơi sở hữu rõ ràng. Các file domain chỉ sử dụng những tên đã khai báo. Định nghĩa trùng lặp có thể khiến parser báo lỗi hoặc làm schema khó bảo trì.

### 9.4. Không phụ thuộc thứ tự tên file

Không dùng tiền tố `01-`, `02-`, `03-` để giả định file nào được parse trước rồi mới đến file khác. Thiết kế schema theo các định nghĩa và extension hợp lệ trên toàn bộ tập resource. Việc tham chiếu một type được khai báo trong file khác là bình thường; schema phải hợp lệ sau khi tất cả resource được nạp.

### 9.5. Chú ý xung đột tên field và enum value

Mỗi object type chỉ có một field với một tên cụ thể. Tương tự, enum không được có các value trùng tên. Khi nhiều domain đóng góp field vào cùng root type, hãy đặt tên đủ cụ thể, ví dụ `book`, `createBook`, `registerMember`, thay vì tên chung chung như `get`, `create` hoặc `search`.

### 9.6. Giữ nullability nhất quán

Khi một domain mở rộng type được định nghĩa ở file khác, cần thống nhất quy ước nullability và ý nghĩa của field. Ví dụ `[Book!]!` cam kết danh sách luôn tồn tại và từng phần tử không null; `Book` cho phép kết quả null. Những cam kết này ảnh hưởng trực tiếp đến response và null propagation của GraphQL.

## 10. Kiểm thử schema nhiều file

Kiểm thử quan trọng nhất là khởi tạo đúng `GraphQlSource` từ toàn bộ resource và thực thi được operation có field đến từ nhiều file.

Với ứng dụng Spring Boot, có thể dùng slice test `@GraphQlTest` và `GraphQlTester`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest
class MultiFileSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void combinesBookAndAuthorFields() {
        graphQlTester.document("""
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
                """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Author One");
    }
}
~~~

Test này giả định slice test có controller/service fixture và dữ liệu chứa một quyển sách với tác giả tên `Author One`. Query chọn `Book` và `Author` cùng lúc, qua đó xác nhận các type tham chiếu từ nhiều file đã cùng tồn tại trong schema cuối cùng và resolver có thể trả dữ liệu.

Nên bổ sung các kiểm tra sau:

1. Application context khởi động thành công khi nạp tất cả schema resources.
2. Root type được khai báo một lần và các file domain mở rộng đúng root type.
3. Query, mutation và subscription field ở nhiều file đều được ánh xạ tới resolver tương ứng.
4. Custom scalar và directive dùng trong file domain đã được đăng ký runtime wiring.
5. File SDL bị thiếu, extension không có type gốc hoặc khai báo trùng được phát hiện khi khởi tạo schema.
6. JAR đóng gói đủ các schema resource, không chỉ hoạt động khi chạy từ IDE.

Nếu cần kiểm tra schema mà không khởi động web server, có thể inject `GraphQlSource` và kiểm tra `schema()` hoặc dùng `ExecutionGraphQlService` cùng `GraphQlTester` phù hợp. Với kiểm thử HTTP endpoint, dùng `HttpGraphQlTester` để kiểm tra thêm routing và transport.

## 11. Lỗi thường gặp khi tổ chức nhiều file

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Type ... not found` | Resource chứa type chưa được nạp hoặc tên type sai | Kiểm tra schema locations, file extension và tên type |
| `Type ... already defined` | Nhiều file cùng khai báo một type gốc | Chuyển phần đóng góp bổ sung sang `extend type` |
| `Cannot extend type ... because it is not defined` | Có extension nhưng thiếu định nghĩa gốc | Tạo type gốc trong file nền tảng và kiểm tra resource path |
| Field đã có trong SDL nhưng client không gọi được | Field chưa nằm trong schema cuối cùng hoặc request đang chạy ứng dụng cũ | Kiểm tra resource discovery, build artifact và khởi động lại ứng dụng |
| Scalar không có implementation | Chỉ khai báo scalar trong SDL | Đăng ký `GraphQLScalarType` trong runtime wiring |
| Chạy IDE được nhưng chạy JAR lỗi | Schema resource không được đóng gói hoặc cấu hình path dùng filesystem | Đặt file dưới `src/main/resources` và dùng classpath resource |
| Hai domain cùng thêm field tên giống nhau | Root type có field name trùng | Đặt tên field theo nghiệp vụ và kiểm tra schema tổng hợp |

Khi gặp lỗi, hãy đọc thông báo schema parse hoặc validation ở thời điểm ứng dụng khởi động. Đó thường là nơi chỉ rõ file, dòng hoặc tên type gây xung đột.

## 12. Quy trình tổ chức schema cho một domain mới

Khi thêm domain mới vào GraphQL API, có thể thực hiện theo thứ tự:

1. Xác định các object type, input type, enum và scalar mà domain cần.
2. Đặt các định nghĩa thuộc domain trong thư mục riêng dưới `src/main/resources/graphql`.
3. Khai báo root type ở file nền tảng; dùng `extend type Query`, `extend type Mutation` hoặc `extend type Subscription` trong file domain.
4. Dùng type dùng chung từ thư mục `common`; không khai báo lại scalar, directive hoặc enum đã tồn tại.
5. Viết resolver Java bằng annotation mapping phù hợp và giữ nghiệp vụ trong service.
6. Kiểm tra schema tổng hợp, runtime wiring, nullability và tên field.
7. Chạy GraphQlTester hoặc integration test để xác nhận operation đi qua nhiều domain hoạt động đúng.

Chia schema theo domain giúp hợp đồng GraphQL phát triển có tổ chức. Điều quan trọng là mọi file vẫn phải tạo thành một schema duy nhất, hợp lệ và nhất quán với resolver, runtime wiring cũng như quy tắc nghiệp vụ của Spring for GraphQL.

## Tài liệu tham khảo

- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot — GraphQL Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#appendix.application-properties.web.spring.graphql.schema)
- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [GraphQL Specification — Type System Extensions](https://spec.graphql.org/October2021/#sec-Type-System-Extensions)
