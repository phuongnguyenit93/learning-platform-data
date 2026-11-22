# Nhiều controller cho một schema

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao một GraphQL schema có thể được xử lý bởi nhiều Spring controller.
- Chia resolver theo root field, object type hoặc miền nghiệp vụ.
- Dùng @QueryMapping, @MutationMapping và @SchemaMapping trong các controller riêng.
- Hiểu cách Spring phát hiện controller và đăng ký mapping cho GraphQL field.
- Tránh xung đột khi nhiều controller cùng khai báo resolver cho một field.
- Kiểm thử nhiều controller cùng tham gia thực thi một GraphQL operation.

## Một schema không yêu cầu một controller duy nhất

Trong Spring for GraphQL, schema SDL mô tả contract của API, còn annotated controller cung cấp resolver cho các field. Một schema có thể có nhiều controller bean cùng tham gia xử lý request.

Ví dụ, API thư viện có các chức năng đọc sách, đọc tác giả, lấy tác giả của một sách và tạo sách. Có thể chia resolver thành BookQueryController, AuthorQueryController, BookFieldController và BookMutationController. Các controller này vẫn phục vụ cùng schema và cùng GraphQL endpoint.

Điều cần nhớ là controller là cách tổ chức code phía server. Nó không tạo một schema riêng, không tạo URL GraphQL riêng và không làm thay đổi cách client viết operation.

## Schema chung cho nhiều controller

Giả sử API thư viện có schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
  booksByAuthor(authorId: ID!): [Book!]!
  authorById(id: ID!): Author
}

type Mutation {
  registerBook(input: RegisterBookInput!): Book!
  renameAuthor(id: ID!, name: String!): Author!
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

input RegisterBookInput {
  title: String!
  authorId: ID!
}
~~~

Schema có một root type Query và một root type Mutation. Mỗi field có thể được ánh xạ đến method trong một controller khác nhau. Book.author là field lồng nhau, có thể có resolver riêng trong một controller chuyên xử lý field của Book.

Một operation có thể đi qua nhiều controller trong cùng lần thực thi:

~~~graphql
query BookDetails($id: ID!) {
  bookById(id: $id) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Root field bookById có thể do BookQueryController xử lý. Khi GraphQL tiếp tục phân giải field author, method trong BookFieldController được gọi. Field name có thể được đọc trực tiếp từ object Author nếu object đã có property hoặc getter tương ứng.

## Cách Spring phát hiện nhiều controller

Một annotated GraphQL controller là Spring bean được đánh dấu bằng @Controller:

~~~java
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {
    // Các method mapping cho GraphQL field.
}
~~~

Spring for GraphQL phát hiện các bean controller trong application context và đăng ký những method có annotation như @QueryMapping, @MutationMapping, @SubscriptionMapping hoặc @SchemaMapping.

Vì vậy, các controller phải được Spring component scan phát hiện. Nếu class nằm trong package con của package chứa lớp @SpringBootApplication, cấu hình component scan mặc định thường đã bao phủ class đó. Nếu đặt controller ngoài phạm vi scan, hãy điều chỉnh @ComponentScan hoặc cấu trúc package để bean được đăng ký.

Ví dụ cấu trúc package:

~~~text
com.example.library
├── LibraryApplication.java
├── graphql
│   ├── book
│   │   ├── BookQueryController.java
│   │   ├── BookFieldController.java
│   │   └── BookMutationController.java
│   └── author
│       ├── AuthorQueryController.java
│       └── AuthorMutationController.java
├── application
│   ├── BookService.java
│   └── AuthorService.java
└── domain
    ├── Book.java
    └── Author.java
~~~

Với LibraryApplication nằm tại com.example.library, các controller trong com.example.library.graphql được component scan mặc định phát hiện. Tổ chức package như vậy giúp nhóm resolver theo miền nghiệp vụ và vẫn giữ service, domain model độc lập với lớp GraphQL.

## Chia root query thành nhiều controller

Các root field thuộc cùng Query có thể được chia theo loại dữ liệu hoặc use case. Ví dụ BookQueryController chỉ xử lý query liên quan đến sách:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Book> booksByAuthor(
            @Argument("authorId") String authorId) {
        return bookService.findByAuthorId(authorId);
    }
}
~~~

Trong khi đó, AuthorQueryController xử lý field authorById:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class AuthorQueryController {

    private final AuthorService authorService;

    public AuthorQueryController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @QueryMapping
    public Author authorById(@Argument("id") String id) {
        return authorService.findById(id).orElse(null);
    }
}
~~~

Hai method thuộc hai bean khác nhau nhưng cùng ánh xạ vào root type Query. Spring for GraphQL đăng ký resolver dựa trên GraphQL type và field name, không dựa trên tên class controller.

Tên method mặc định được dùng làm tên field. Nếu muốn tên Java khác tên field trong SDL, có thể khai báo tên tường minh:

~~~java
@QueryMapping(name = "bookById")
public Book findBook(@Argument("id") String bookId) {
    return bookService.findById(bookId).orElse(null);
}
~~~

Khi dùng tên tường minh, hãy bảo đảm tên đó khớp chính xác với field trong schema. Tên method Java không cần trùng tên field nếu mapping đã chỉ rõ.

## Tách resolver cho field lồng nhau

Không phải mọi resolver đều thuộc root Query hoặc Mutation. Các field trên object type có thể được đặt trong controller riêng. Ví dụ Book.author được xử lý trong BookFieldController:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
@SchemaMapping(typeName = "Book")
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId()).orElse(null);
    }
}
~~~

@SchemaMapping(typeName = "Book") ở cấp class đặt GraphQL object type mặc định cho các method mapping trong controller. @SchemaMapping trên method author dùng tên method làm field name, nên ánh xạ đến Book.author.

Tham số Book book là source object mà GraphQL đang phân giải. Spring for GraphQL tự truyền object cha vào method; không cần khai báo @Argument cho source object.

Nếu không muốn đặt mapping mặc định ở cấp class, có thể khai báo đầy đủ trên method:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author resolveBookAuthor(Book source) {
    return authorService.findById(source.authorId()).orElse(null);
}
~~~

Cách thứ hai hữu ích khi tên method không giống field GraphQL hoặc một controller xử lý field thuộc nhiều object type khác nhau.

Không cần viết resolver cho mọi field. Nếu object Java đã có property hoặc getter tương ứng, GraphQL có thể đọc giá trị bằng property data fetcher mặc định. Chỉ tạo @SchemaMapping khi cần truy vấn nguồn dữ liệu khác, biến đổi kết quả hoặc thực hiện logic bổ sung.

## Tách mutation theo use case

Mutation cũng có thể được chia thành các controller theo miền. Ví dụ:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book registerBook(
            @Argument("input") RegisterBookInput input) {
        return bookService.register(input);
    }
}
~~~

Một controller khác có thể xử lý việc đổi tên tác giả:

~~~java
@Controller
public class AuthorMutationController {

    private final AuthorService authorService;

    public AuthorMutationController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @MutationMapping
    public Author renameAuthor(
            @Argument("id") String id,
            @Argument("name") String name) {
        return authorService.rename(id, name);
    }
}
~~~

RegisterBookInput có thể là DTO hoặc record:

~~~java
public record RegisterBookInput(String title, String authorId) {
}
~~~

Các controller gọi application service để thực hiện nghiệp vụ. Không nên gọi trực tiếp method của controller khác hoặc đặt logic nghiệp vụ dùng chung trong controller. Nếu nhiều resolver cần cùng một hành vi, hãy đưa hành vi đó vào service hoặc một thành phần ứng dụng phù hợp.

## Một GraphQL field chỉ nên có một mapping

Spring for GraphQL cần xác định duy nhất resolver cho mỗi field được ánh xạ. Nếu hai controller cùng đăng ký một mapping cho Query.bookById, ứng dụng có thể gặp lỗi ambiguous mapping khi khởi tạo GraphQL handler.

Ví dụ không nên tạo hai method sau trong hai controller khác nhau:

~~~java
@Controller
class FirstBookController {
    @QueryMapping
    Book bookById(@Argument("id") String id) {
        // ...
    }
}

@Controller
class SecondBookController {
    @QueryMapping
    Book bookById(@Argument("id") String id) {
        // ...
    }
}
~~~

Cả hai method cùng nhắm đến field Query.bookById. GraphQL không tự chọn controller theo package, tên class hoặc thứ tự component scan.

Nếu hai use case khác nhau cần tìm sách, hãy chọn một trong các cách:

- Tạo các field GraphQL riêng với tên và semantics rõ ràng.
- Giữ một resolver duy nhất rồi ủy quyền cho các service hoặc strategy phù hợp.
- Chia logic dùng chung thành service, nhưng chỉ để một method đăng ký mapping cho field đó.

Không dùng nhiều controller để tạo nhiều phiên bản resolver cạnh tranh cho cùng một field. Một mapping duy nhất giúp schema và luồng thực thi dễ dự đoán.

## Phân chia controller theo tiêu chí nào?

Không có một cấu trúc duy nhất phù hợp cho mọi ứng dụng. Có thể chọn cách chia dựa trên quy mô schema, ranh giới nghiệp vụ và cách nhóm phát triển sở hữu code.

| Cách chia | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| Theo root operation | Query và mutation có số lượng field lớn, cần tách trách nhiệm đọc/ghi | BookQueryController, BookMutationController |
| Theo object type | Nhiều field lồng nhau thuộc một type cần logic riêng | BookFieldController, OrderFieldController |
| Theo miền nghiệp vụ | Schema lớn, nhiều nhóm phụ trách các miền độc lập | catalog, sales, identity |
| Theo use case | Một miền có các nhóm thao tác khác nhau và ranh giới rõ | BookSearchController, BookAdministrationController |

Một số nguyên tắc thực tế:

- Giữ mỗi controller tập trung vào một nhóm mapping có liên quan.
- Tránh một controller khổng lồ chứa mọi field của toàn schema.
- Tránh tạo một controller cho mỗi field đơn giản nếu điều đó khiến code bị phân mảnh quá mức.
- Để service chịu trách nhiệm nghiệp vụ, transaction và truy cập dữ liệu.
- Giữ tên GraphQL field ổn định ngay cả khi đổi tên class hoặc package Java.
- Dùng package theo miền nghiệp vụ để component scan và quyền sở hữu code dễ hiểu.

## Luồng thực thi khi nhiều controller cùng tham gia

Một operation có thể đi qua nhiều resolver thuộc nhiều controller:

~~~mermaid
flowchart TD
    A[Client gửi BookDetails] --> B[GraphQL endpoint]
    B --> C[GraphQL schema và runtime]
    C --> D[BookQueryController.bookById]
    D --> E[BookService]
    E --> F[Trả về Book]
    F --> G[BookFieldController.author]
    G --> H[AuthorService]
    H --> I[Trả về Author]
    I --> J[Property data fetcher đọc Author.name]
    J --> K[Ghép GraphQL response]
~~~

Mỗi resolver chỉ cung cấp dữ liệu cho field mà nó phụ trách. GraphQL runtime điều phối thứ tự thực thi theo operation và selection set. Client không cần biết field được xử lý bởi một controller hay nhiều controller.

Việc tách controller cũng không tự giải quyết vấn đề hiệu năng. Nếu BookFieldController.author gọi database một lần cho từng sách trong danh sách, query có thể gặp N+1. Khi cần, hãy xem xét @BatchMapping, DataLoader hoặc chiến lược truy vấn theo lô. Nhiều controller vẫn dùng chung các cơ chế tối ưu resolver đó.

## Bảo mật và xử lý lỗi không phụ thuộc số controller

Tách controller không tạo ranh giới bảo mật tự động. Tất cả mapping vẫn thuộc cùng GraphQL schema và cùng endpoint. Nếu field chứa dữ liệu nhạy cảm, hãy kiểm tra quyền ở resolver, method security hoặc service để bảo đảm mọi đường truy cập đều được bảo vệ.

Ví dụ, BookFieldController có thể trả về Book.internalNotes chỉ khi người dùng có quyền phù hợp. Chuyển resolver sang controller khác không làm field trở nên riêng tư. Tương tự, validation, exception handling và transaction nên được tổ chức ở tầng phù hợp với trách nhiệm của chúng.

## Kiểm thử nhiều controller cùng một schema

GraphQlTester kiểm thử operation qua GraphQL runtime mà không yêu cầu client biết resolver nằm ở controller nào. Ví dụ query có thể kiểm tra cả root field và field lồng nhau:

~~~java
graphQlTester.document("""
        query BookDetails($id: ID!) {
            bookById(id: $id) {
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
    .execute()
    .path("bookById.author.name")
    .entity(String.class)
    .isEqualTo("Nguyen An");
~~~

Test này xác minh operation đi qua resolver của bookById, tiếp tục phân giải Book.author và đọc Author.name. Trong test slice với @GraphQlTest, hãy đưa các controller liên quan vào test context và mock các service phụ thuộc. Integration test dùng application context đầy đủ có thể xác minh component scan và tất cả controller bean được đăng ký.

Nên có các kiểm thử sau:

1. Tất cả controller cần thiết được Spring phát hiện.
2. Mỗi field được ánh xạ đúng một resolver.
3. Root field từ các controller khác nhau cùng hoạt động trong một schema.
4. Field lồng nhau nhận đúng source object.
5. Operation kết hợp field từ nhiều controller trả về response đúng.
6. Mapping trùng field khiến test context thất bại, để lỗi được phát hiện sớm.
7. Quyền truy cập và lỗi nghiệp vụ vẫn được xử lý đúng khi resolver được chia thành nhiều class.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Controller không được gọi | Class nằm ngoài component scan hoặc thiếu @Controller | Kiểm tra package và application context |
| Field không tìm thấy resolver | Tên field hoặc typeName không khớp schema | Kiểm tra SDL và annotation mapping |
| Ứng dụng lỗi khi khởi động do mapping | Nhiều method đăng ký cùng GraphQL field | Giữ một mapping duy nhất cho mỗi field |
| Field lồng nhau nhận source sai | Khai báo nhầm source parameter hoặc typeName | Kiểm tra object type và kiểu tham số method |
| Tách controller nhưng code khó bảo trì | Chia quá nhỏ hoặc đưa nghiệp vụ vào controller | Nhóm theo domain/use case và chuyển nghiệp vụ sang service |
| Query nhiều object bị chậm | Resolver lồng nhau truy cập dữ liệu từng phần tử | Dùng batching hoặc DataLoader khi phù hợp |
| Nghĩ rằng controller riêng đã được bảo vệ | Nhầm ranh giới code với ranh giới authorization | Kiểm tra quyền ở service/resolver theo từng field |

## Thực hành tổng hợp

Với schema thư viện ở đầu bài, hãy chia resolver thành các controller:

1. BookQueryController xử lý bookById và booksByAuthor.
2. AuthorQueryController xử lý authorById.
3. BookFieldController xử lý Book.author.
4. BookMutationController xử lý registerBook.
5. AuthorMutationController xử lý renameAuthor.

Đặt các controller dưới package được Spring Boot component scan. Mỗi controller inject service tương ứng qua constructor. Sau đó:

- Gửi một query lấy sách cùng tác giả để xác minh nhiều controller tham gia một operation.
- Gửi mutation tạo sách và kiểm tra object trả về.
- Thử khai báo mapping trùng Query.bookById để quan sát lỗi đăng ký mapping.
- Kiểm tra service vẫn là nơi thực hiện nghiệp vụ và quyền truy cập.
- Nếu query danh sách tạo nhiều lần gọi lấy tác giả, thử chuyển resolver sang cơ chế batch ở bài học phù hợp.

## Ghi nhớ

Một GraphQL schema có thể được xử lý bởi nhiều Spring @Controller bean. @QueryMapping và @MutationMapping ánh xạ root field; @SchemaMapping ánh xạ field trên object type. Spring phát hiện controller qua component scan và đăng ký mapping theo GraphQL type cùng field name. Có thể chia controller theo root operation, object type, miền nghiệp vụ hoặc use case, nhưng mỗi field chỉ nên có một mapping. Controller điều phối service; schema, endpoint, bảo mật và contract của API vẫn được quản lý ở cấp ứng dụng.
