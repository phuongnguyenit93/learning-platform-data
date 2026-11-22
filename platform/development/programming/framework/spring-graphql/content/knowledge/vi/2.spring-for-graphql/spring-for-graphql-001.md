# Spring for GraphQL là gì

Spring for GraphQL là dự án trong hệ sinh thái Spring giúp xây dựng GraphQL server bằng Spring Framework. Nó kết nối bộ thực thi GraphQL Java với các cơ chế quen thuộc của Spring như dependency injection, quản lý bean, cấu hình ứng dụng, Spring Boot, Spring Security và kiểm thử. Nhờ đó, ứng dụng Java có thể cung cấp GraphQL API mà không phải tự xây dựng toàn bộ lớp tiếp nhận request, ánh xạ schema và gọi nghiệp vụ.

Spring for GraphQL phù hợp khi ứng dụng cần cung cấp một API theo mô hình đồ thị dữ liệu: client mô tả những trường muốn nhận, còn server chịu trách nhiệm xác thực operation và phân giải từng trường theo schema. Thư viện không tự tạo ra nghiệp vụ hay tự biến cơ sở dữ liệu thành GraphQL API. Nhà phát triển vẫn định nghĩa hợp đồng API, viết resolver và quyết định cách truy cập dữ liệu.

## GraphQL giải quyết vấn đề gì?

Với REST, mỗi endpoint thường đại diện cho một tài nguyên hoặc một hành động. Một màn hình cần thông tin sách, tác giả và đánh giá có thể phải gọi nhiều endpoint. Nếu endpoint trả về quá nhiều trường, client nhận dữ liệu không cần thiết; nếu endpoint trả về quá ít, client phải gọi thêm request.

GraphQL cho phép client gửi một operation mô tả chính xác cấu trúc dữ liệu cần nhận. Ví dụ, client có thể yêu cầu thông tin sách cùng tên tác giả trong một request:

~~~graphql
query {
  book(id: "book-101") {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Server trả về dữ liệu có cấu trúc tương ứng với selection set:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring in Action",
      "author": {
        "id": "author-12",
        "name": "Craig Walls"
      }
    }
  }
}
~~~

GraphQL API được mô tả bằng một schema có kiểu dữ liệu rõ ràng. Schema quy định những operation nào được phép gọi, các trường có kiểu gì, trường nào bắt buộc và các kiểu dữ liệu liên kết với nhau ra sao. Client có thể chọn trường trong phạm vi schema, nhưng không thể yêu cầu một trường tùy ý mà server chưa công bố.

GraphQL là ngôn ngữ truy vấn và mô hình thực thi API, không phải ngôn ngữ truy vấn cơ sở dữ liệu. Một resolver có thể đọc dữ liệu từ database, gọi REST service khác, lấy dữ liệu từ cache hoặc kết hợp nhiều nguồn. Schema GraphQL là hợp đồng của API; nó không nhất thiết giống cấu trúc bảng hay entity trong hệ thống lưu trữ.

## Spring for GraphQL nằm ở đâu trong kiến trúc?

Spring for GraphQL sử dụng GraphQL Java làm nền tảng thực thi. GraphQL Java phụ trách những công việc cốt lõi như phân tích operation, kiểm tra operation theo schema và thực thi các field. Spring for GraphQL bổ sung cách tích hợp những công việc đó vào ứng dụng Spring.

Một ứng dụng thường có các thành phần sau:

- **Schema SDL** mô tả kiểu dữ liệu và các field mà API công bố.
- **GraphQlSource** cung cấp schema và cấu hình runtime cho bộ thực thi GraphQL.
- **Controller và resolver** ánh xạ field trong schema tới phương thức Java.
- **Service và repository** thực hiện nghiệp vụ, truy cập dữ liệu hoặc gọi hệ thống khác.
- **Transport handler** tiếp nhận GraphQL request qua HTTP, WebSocket hoặc transport được cấu hình phù hợp.
- **GraphQL Java** thực thi operation và tạo kết quả theo schema.

Luồng xử lý HTTP ở mức khái quát:

~~~mermaid
flowchart TD
    A["GraphQL client"] -->|"POST /graphql"| B["HTTP handler"]
    B --> C["ExecutionGraphQlService"]
    C --> D["GraphQL Java"]
    D --> E["Resolver trong Spring Controller"]
    E --> F["Service"]
    F --> G["Repository / hệ thống ngoài"]
    G --> F
    F --> E
    E --> D
    D --> H["GraphQL response: data và errors"]
    H --> A
~~~

Trước khi nhận request, Spring tạo GraphQL runtime từ schema và các cấu hình mapping. Khi có request, lớp transport chuyển operation và variables cho dịch vụ thực thi. GraphQL Java kiểm tra operation, sau đó gọi resolver tương ứng với những field cần phân giải. Resolver có thể gọi service; kết quả được GraphQL Java ghép lại theo cấu trúc client yêu cầu.

Trong ứng dụng Spring Boot, phần lớn cấu hình nền tảng được tự động thiết lập khi có dependency phù hợp. Nhà phát triển vẫn cần cung cấp schema, resolver và cấu hình bổ sung cho các yêu cầu riêng như bảo mật, transport hoặc xử lý lỗi.

## Schema SDL là hợp đồng của GraphQL API

Spring for GraphQL thường sử dụng cách tiếp cận schema-first: khai báo schema bằng GraphQL Schema Definition Language (SDL), sau đó ánh xạ field của schema vào mã Java. Một schema nhỏ cho nghiệp vụ sách có thể như sau:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Subscription {
  bookCreated: Book!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Ba root type thường gặp có vai trò khác nhau:

| Root type | Mục đích | Ví dụ |
| --- | --- | --- |
| **Query** | Đọc dữ liệu, không biểu diễn thao tác ghi | Lấy một sách hoặc danh sách sách |
| **Mutation** | Thực hiện thay đổi dữ liệu hoặc trạng thái | Tạo, cập nhật hoặc xóa sách |
| **Subscription** | Nhận sự kiện được phát ra theo thời gian | Nhận thông báo khi có sách mới |

Một số ký hiệu trong SDL cần được hiểu chính xác:

- **ID** là scalar thường dùng cho định danh. Trong Java, giá trị này thường được ánh xạ sang **String**.
- Dấu **!** biểu thị giá trị không được null. **ID!** nghĩa là bắt buộc có ID.
- **[Book!]!** nghĩa là danh sách không được null và từng phần tử trong danh sách cũng không được null.
- **input** khai báo cấu trúc dữ liệu đầu vào. Input object dùng để gom các tham số có liên quan của mutation hoặc field.
- **type** khai báo kiểu dữ liệu đầu ra mà client có thể truy vấn.

Schema là ranh giới công khai của API. Một thuộc tính tồn tại trong Java object sẽ không tự động trở thành field công khai nếu schema không khai báo nó. Ngược lại, mỗi field trong schema cần có cách phân giải phù hợp, có thể dùng property access mặc định hoặc resolver do ứng dụng cung cấp.

## Tích hợp Spring Boot

Với Gradle và Spring Boot, dependency cơ bản có thể khai báo như sau:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Spring Boot quản lý phiên bản tương thích của các thư viện khi dự án sử dụng dependency management của Boot. **spring-boot-starter-graphql** đưa Spring for GraphQL vào ứng dụng. **spring-boot-starter-web** cung cấp nền tảng Spring MVC để phục vụ GraphQL qua HTTP. Nếu ứng dụng dùng reactive stack, có thể chọn **spring-boot-starter-webflux** thay cho starter MVC.

Đặt file schema trong thư mục resource, ví dụ:

~~~text
src/main/resources/
└── graphql/
    └── schema.graphqls
~~~

Spring Boot tự động tìm schema trong thư mục GraphQL mặc định và cấu hình endpoint HTTP là **/graphql**. Có thể thay đổi đường dẫn bằng thuộc tính **spring.graphql.path**. Việc có starter GraphQL không đồng nghĩa ứng dụng đã có API nghiệp vụ: schema và các resolver tương ứng vẫn phải được viết.

## Ánh xạ schema vào Java bằng annotation

Spring for GraphQL cung cấp các annotation để khai báo phương thức xử lý field. Các phương thức này thường nằm trong bean được đánh dấu **@Controller**.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @MutationMapping
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return bookService.findAuthor(book.authorId());
    }
}
~~~

Trong ví dụ:

- **@QueryMapping** ánh xạ phương thức vào field thuộc root type **Query**. Tên phương thức mặc định được dùng làm tên field, trừ khi cấu hình tên khác.
- **@MutationMapping** ánh xạ phương thức vào field thuộc root type **Mutation**.
- **@SchemaMapping** ánh xạ một field cụ thể của một kiểu dữ liệu. Tham số nguồn **Book book** đại diện cho object cha mà GraphQL đang phân giải.
- **@Argument** lấy giá trị argument từ operation GraphQL và chuyển đổi sang kiểu Java tương ứng.

Ví dụ kiểu đầu vào có thể biểu diễn bằng Java record:

~~~java
public record CreateBookInput(String title, String authorId) {
}
~~~

Khi client gọi field **createBook**, Spring chuyển input object theo schema thành **CreateBookInput**, rồi truyền vào phương thức controller. Controller gọi service để thực hiện nghiệp vụ. Cách tổ chức này giữ cho resolver tập trung vào việc nối schema với ứng dụng, còn quy tắc nghiệp vụ nằm trong service.

**@SchemaMapping** cũng có thể được viết ngắn hơn khi tên field và kiểu nguồn có thể suy ra từ tên phương thức và tham số. Khi schema có nhiều kiểu hoặc tên phương thức không trùng field, khai báo rõ **typeName** và **field** giúp mapping dễ đọc hơn.

## Query, Mutation và Subscription trong ứng dụng

**Query** dùng để đọc dữ liệu. Client có thể gửi nhiều field trong cùng một operation và chọn các trường lồng nhau. Resolver của Query nên tập trung vào việc trả dữ liệu, tránh tạo ra thay đổi trạng thái ngoài ý muốn.

**Mutation** dùng cho thao tác làm thay đổi dữ liệu. Các mutation thường nhận một input object để tránh danh sách argument dài và giúp schema dễ mở rộng. Kiểm tra dữ liệu đầu vào, quyền thực hiện và quy tắc nghiệp vụ vẫn thuộc trách nhiệm của ứng dụng.

**Subscription** dùng để nhận dữ liệu khi có sự kiện mới. Trong Spring for GraphQL, phương thức được đánh dấu **@SubscriptionMapping** có thể trả về một reactive publisher, chẳng hạn **Flux<Book>**. Để client nhận được luồng sự kiện, ứng dụng phải cấu hình transport hỗ trợ subscription, ví dụ WebSocket hoặc RSocket. Chỉ khai báo root type **Subscription** trong SDL chưa đủ để tạo một kênh truyền sự kiện hoạt động.

Ví dụ operation có biến giúp tách dữ liệu đầu vào khỏi câu truy vấn:

~~~graphql
query GetBook($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

Request HTTP có thể gửi operation và variables dưới dạng JSON:

~~~json
{
  "operationName": "GetBook",
  "query": "query GetBook($id: ID!) { book(id: $id) { id title author { name } } }",
  "variables": {
    "id": "book-101"
  }
}
~~~

GraphQL response thường có **data**; nếu có lỗi trong quá trình xử lý, response có thể có thêm **errors**. Một số field vẫn có thể trả dữ liệu thành công trong khi field khác phát sinh lỗi, tùy vị trí lỗi và quy tắc nullability của schema. Vì vậy, client cần đọc cả **data** lẫn **errors**, thay vì chỉ dựa vào mã HTTP để kết luận operation thành công hoàn toàn.

## Giải quyết quan hệ dữ liệu và vấn đề N+1

GraphQL cho phép client truy vấn field lồng nhau, nên một query lấy danh sách sách và tác giả có thể khiến server phân giải field **author** nhiều lần. Nếu mỗi resolver truy vấn database riêng, một request có thể tạo ra một truy vấn lấy danh sách sách và thêm N truy vấn lấy tác giả. Đây là vấn đề N+1.

Spring for GraphQL cung cấp **@BatchMapping** để gom việc phân giải cùng một field cho nhiều object nguồn. Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> authors(List<Book> books) {
    return authorService.findAuthorsFor(books);
}
~~~

Thay vì gọi service một lần cho từng quyển sách, phương thức nhận một nhóm **Book** và trả về kết quả tương ứng cho từng object. Cách này phù hợp khi service hoặc repository có thể tải dữ liệu theo lô.

Một lựa chọn khác là DataLoader. DataLoader gom các lần yêu cầu key trong cùng một lượt thực thi thành một batch load và có thể lưu kết quả trong phạm vi request. Spring for GraphQL hỗ trợ đăng ký batch loader và đưa DataLoader vào tham số resolver. Việc chọn **@BatchMapping** hay DataLoader tùy vào cách tổ chức truy cập dữ liệu; cả hai đều cần batch query thực sự ở tầng service/repository để giảm số lần gọi tới nguồn dữ liệu.

Ngoài N+1, API cần xem xét phân trang cho danh sách lớn, giới hạn độ sâu hoặc độ phức tạp của operation, timeout và giới hạn tài nguyên. Vì client được quyền chọn field, một query hợp lệ về mặt schema vẫn có thể tốn nhiều tài nguyên nếu truy vấn quá sâu hoặc yêu cầu lượng dữ liệu lớn.

## Xử lý lỗi, validation và bảo mật

GraphQL phân biệt lỗi cú pháp, lỗi validation theo schema và lỗi trong quá trình thực thi resolver. Spring for GraphQL cho phép tùy chỉnh cách chuyển exception từ resolver thành GraphQL error thông qua cơ chế như **DataFetcherExceptionResolver**. Ứng dụng nên trả thông tin đủ hữu ích cho client nhưng không để lộ stack trace, câu SQL, thông tin xác thực hoặc chi tiết nội bộ.

Input từ client cần được kiểm tra trước khi thực hiện nghiệp vụ. Có thể kết hợp kiểu input trong SDL với validation ở tầng Java, chẳng hạn Jakarta Bean Validation, rồi chuyển các lỗi validation thành thông báo GraphQL phù hợp. Schema giúp kiểm tra kiểu và nullability, nhưng không thay thế các quy tắc nghiệp vụ như giới hạn số lượng, trạng thái hợp lệ hoặc quyền sở hữu dữ liệu.

Về bảo mật, cần kiểm soát cả request tới endpoint lẫn quyền truy cập từng field hoặc từng bản ghi. Spring Security có thể bảo vệ endpoint HTTP và áp dụng method security trên các phương thức resolver, ví dụ bằng **@PreAuthorize**. Với query lồng nhiều cấp, chỉ xác thực người dùng ở endpoint là chưa đủ: resolver vẫn phải kiểm tra người dùng có quyền xem object hoặc field đang được yêu cầu hay không. Các truy vấn theo tenant cũng phải áp dụng điều kiện tenant ở tầng truy cập dữ liệu.

## Kiểm thử GraphQL API

Spring for GraphQL cung cấp **GraphQlTester** để kiểm thử operation mà không buộc test phải tự xử lý chi tiết JSON request và response. Tùy loại test, có thể dùng tester trực tiếp với execution service hoặc tester gắn với transport HTTP.

Ví dụ kiểm thử một query:

~~~java
graphQlTester.document("""
        query GetBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
~~~

Test nên kiểm tra cả kết quả đúng, trường hợp không tìm thấy dữ liệu, input không hợp lệ, người dùng thiếu quyền và lỗi từ nguồn dữ liệu. Với mutation, cần xác minh thay đổi nghiệp vụ thực sự xảy ra. Với subscription, cần kiểm tra luồng sự kiện và transport được cấu hình.

## Khi nào nên dùng Spring for GraphQL?

Spring for GraphQL phù hợp khi ứng dụng cần một hợp đồng dữ liệu linh hoạt cho nhiều loại client, khi dữ liệu đến từ nhiều domain hoặc service, hoặc khi client cần kết hợp các quan hệ dữ liệu trong một operation. Nó đặc biệt hữu ích khi frontend thay đổi cách hiển thị thường xuyên và cần chọn tập field phù hợp cho từng màn hình.

GraphQL không bắt buộc phải thay thế toàn bộ REST API. Một hệ thống có thể dùng REST cho các endpoint tài nguyên hoặc tác vụ phù hợp, đồng thời dùng GraphQL cho những màn hình cần kết hợp nhiều nguồn dữ liệu. Quyết định nên dựa trên nhu cầu của client, độ phức tạp schema, yêu cầu caching, bảo mật và khả năng vận hành.

Khi triển khai thực tế, cần theo dõi thời gian thực thi theo operation và resolver, số lần gọi tới database hoặc service ngoài, kích thước response và tần suất lỗi. Những số liệu này giúp phát hiện resolver chậm, N+1, query quá tốn tài nguyên và điểm nghẽn trong từng nhánh của graph.

Spring for GraphQL cung cấp lớp tích hợp để xây dựng GraphQL server theo cách tự nhiên trong ứng dụng Spring: schema mô tả hợp đồng, annotation ánh xạ field vào Java, service xử lý nghiệp vụ, còn GraphQL Java thực thi operation. Hiểu rõ ranh giới giữa các phần này giúp thiết kế API dễ kiểm thử, kiểm soát quyền truy cập và tối ưu khi dữ liệu có nhiều quan hệ.
