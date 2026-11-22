# Execute query

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của GraphQlTester khi thực thi một GraphQL query trong test.
- Tạo request từ GraphQL document, operation name và variables.
- Gọi execute() và đọc GraphQL response.
- Trích xuất field bằng JsonPath và ánh xạ thành Java object.
- Kiểm tra scalar, object, list và cấu trúc JSON.
- Đọc và xác nhận GraphQL errors, kể cả khi response có partial data.
- Tải query từ file trên classpath và ghép fragment.
- Chọn GraphQlTester phù hợp với phạm vi kiểm thử.
- Phân biệt kiểm thử execution với kiểm thử HTTP transport.
- Viết test cho Query thành công, không tìm thấy dữ liệu và lỗi resolver.

## 1. Execute query trong kiểm thử GraphQL là gì?

Khi xây dựng GraphQL server, việc kiểm tra riêng một service method chưa đủ để bảo đảm API hoạt động đúng. Một query đi qua nhiều bước: GraphQL document được parse, kiểm tra theo schema, variables được coercion, field được ánh xạ tới DataFetcher, resolver gọi service và kết quả được serialize thành GraphQL response.

Spring for GraphQL cung cấp GraphQlTester để thực thi GraphQL request trong test và kiểm tra response theo cùng một workflow, độc lập với transport được sử dụng.

Một test thường có dạng:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "b-01") {
                id
                title
            }
        }
        """)
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Luồng trên có các bước:

1. document(...) cung cấp GraphQL operation.
2. execute() thực thi request thông qua GraphQlTester đã cấu hình.
3. path(...) chọn dữ liệu trong response bằng JsonPath.
4. entity(...) giải mã giá trị thành kiểu Java.
5. isEqualTo(...) xác nhận giá trị thực tế bằng giá trị mong đợi.

Trong bài này, từ execute query chủ yếu nói tới việc chạy một request GraphQL trong test. Cần phân biệt nó với execute() của GraphQlTester: execute() là method bắt đầu thực thi request đã khai báo, còn query là loại operation mà document yêu cầu server chạy.

## 2. GraphQlTester và các kiểu tester

GraphQlTester là abstraction chung để viết test GraphQL. Cùng một cách tạo document, truyền variables, execute và kiểm tra response có thể được dùng với nhiều kiểu transport.

Spring for GraphQL cung cấp các implementation phù hợp với những phạm vi kiểm thử khác nhau:

| Tester | Phạm vi kiểm thử | Có cần HTTP server không? |
|---|---|---|
| ExecutionGraphQlServiceTester | Thực thi qua ExecutionGraphQlService | Không |
| WebGraphQlTester | Thực thi qua WebGraphQlHandler, gồm interceptor chain | Không cần HTTP server |
| HttpGraphQlTester | Gửi request qua HTTP tới server | Có thể dùng live server hoặc mock web transport |
| WebSocketGraphQlTester | Gửi operation qua WebSocket | Cần WebSocket transport được cấu hình |
| RSocketGraphQlTester | Gửi operation qua RSocket | Cần RSocket transport |

Với bài kiểm tra Query thông thường, có thể dùng GraphQlTester được Spring Boot tự cấu hình trong test slice hoặc ExecutionGraphQlServiceTester. Nếu cần xác nhận HTTP endpoint, headers, authentication và status code, dùng HttpGraphQlTester kết hợp test web phù hợp.

GraphQlTester giúp kiểm tra đường đi từ GraphQL document tới response. Nó không tự thay thế unit test của service hoặc repository. Hãy chọn tầng test theo hành vi muốn xác nhận.

## 3. Thêm thư viện kiểm thử

Spring for GraphQL cung cấp module riêng chứa GraphQlTester. Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle:

~~~groovy
testImplementation("org.springframework.graphql:spring-graphql-test")
~~~

Nếu kiểm thử qua HTTP bằng WebTestClient và ứng dụng chưa có WebFlux trên test classpath, có thể cần thêm starter WebFlux ở test scope:

~~~groovy
testImplementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

Với ứng dụng Spring MVC, có thể dùng MockMvcWebTestClient để tạo HttpGraphQlTester mà không cần đổi web stack sang WebFlux. Chọn đúng test client theo transport của ứng dụng.

Dùng Spring Boot dependency management để chọn phiên bản tương thích giữa Spring Boot, Spring for GraphQL và spring-graphql-test. Không tự chọn một phiên bản test module khác với dependency line mà ứng dụng đang sử dụng.

## 4. Chuẩn bị schema, controller và model

Giả sử ứng dụng có Query lấy sách theo ID.

Schema trong file src/main/resources/graphql/schema.graphqls:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Model:

~~~java
public record Book(
        String id,
        String title,
        Integer publishedYear) {
}
~~~

Service:

~~~java
public interface BookService {
    Book findById(String id);
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Query field bookById nhận argument id và trả về Book hoặc null nếu không tìm thấy. Vì field Book được khai báo nullable trong SDL, server có thể trả null mà không bắt buộc tạo execution error.

Test cần xác nhận nhiều lớp cùng hoạt động:

- Schema nhận diện Query và field bookById.
- Argument id được bind đúng.
- @QueryMapping được gọi.
- Service nhận đúng ID.
- Book được serialize theo field mà client chọn.

## 5. Viết controller test bằng @GraphQlTest

Spring Boot cung cấp @GraphQlTest để kiểm thử GraphQL controller mà không cần khởi động HTTP server. Annotation này cấu hình GraphQL infrastructure và chỉ nạp nhóm bean phù hợp cho GraphQL test.

Ví dụ:

~~~java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void shouldReturnBookById() {
        when(bookService.findById("b-01"))
                .thenReturn(new Book(
                        "b-01",
                        "GraphQL in Practice",
                        2026));

        graphQlTester.document("""
                query BookById($id: ID!) {
                    bookById(id: $id) {
                        id
                        title
                        publishedYear
                    }
                }
                """)
                .operationName("BookById")
                .variable("id", "b-01")
                .execute()
                .path("bookById.id")
                .entity(String.class)
                .isEqualTo("b-01");
    }
}
~~~

Trong ví dụ:

- @GraphQlTest(BookController.class) chỉ tập trung vào controller được chỉ định và GraphQL infrastructure liên quan.
- GraphQlTester được tự động cấu hình.
- @MockitoBean cung cấp mock BookService vì service thông thường không tự được nạp trong test slice.
- when(...).thenReturn(...) thiết lập dữ liệu cho test.
- execute() chạy Query qua GraphQL engine.
- path(...) chọn field trong response để assertion.

Với Spring Boot 4, package của @GraphQlTest là org.springframework.boot.graphql.test.autoconfigure. Với Spring Boot 3, package là org.springframework.boot.test.autoconfigure.graphql. Spring Framework mới hỗ trợ @MockitoBean; với project Boot cũ hơn, có thể cần dùng @MockBean theo phiên bản đang sử dụng.

Trong Boot 4, annotation @GraphQlTest được cung cấp bởi module spring-boot-graphql-test. @MockitoBean nằm trong package org.springframework.test.context.bean.override.mockito. Với Boot 3.4 trở lên cũng có thể dùng @MockitoBean; các phiên bản Boot cũ hơn thường dùng @MockBean từ Spring Boot.

@GraphQlTest không phải full application test. Các service, repository hoặc configuration không nằm trong tập bean được scan cần được cung cấp bằng mock hoặc @Import.

## 6. Tạo request bằng document()

document(String) nhận GraphQL document dưới dạng chuỗi. Document có thể chứa một hoặc nhiều operation, fragment và variable definition.

Ví dụ query đơn giản:

~~~java
graphQlTester.document("{ bookById(id: \"b-01\") { id title } }")
        .execute()
        .path("bookById.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
~~~

Với query dài, Java text block giúp giữ cấu trúc GraphQL dễ đọc:

~~~java
String query = """
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """;

graphQlTester.document(query)
        .execute()
        .path("bookById")
        .matchesJson("""
                {
                    "id": "b-01",
                    "title": "GraphQL in Practice"
                }
                """);
~~~

document() chỉ tạo request specification. Request chỉ được thực thi khi gọi execute() hoặc một phương thức thực thi tương ứng như executeAndVerify() hay executeSubscription().

Không nên nối chuỗi bằng cách đưa trực tiếp input vào GraphQL document. Hãy dùng variables để giữ query ổn định và tránh lỗi escaping.

## 7. Truyền variables và operationName

Query thường khai báo biến để tách cấu trúc operation khỏi dữ liệu đầu vào.

Ví dụ:

~~~graphql
query SearchBooks($keyword: String!, $first: Int!) {
  searchBooks(keyword: $keyword, first: $first) {
    id
    title
  }
}
~~~

Trong test:

~~~java
graphQlTester.document("""
        query SearchBooks($keyword: String!, $first: Int!) {
            searchBooks(keyword: $keyword, first: $first) {
                id
                title
            }
        }
        """)
        .operationName("SearchBooks")
        .variable("keyword", "Spring")
        .variable("first", 10)
        .execute()
        .path("searchBooks")
        .entityList(Book.class)
        .hasSize(10);
~~~

Có thể truyền nhiều variables qua Map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 10
);

graphQlTester.document(query)
        .operationName("SearchBooks")
        .variables(variables)
        .execute();
~~~

operationName cần thiết khi document chứa nhiều operation để server biết operation nào được yêu cầu. Với document chỉ có một operation, có thể bỏ qua operationName, nhưng đặt tên vẫn giúp test và log dễ đọc.

GraphQL server vẫn validate kiểu biến theo SDL. Test nên bao gồm cả biến hợp lệ, biến sai kiểu, biến bắt buộc bị thiếu và biến nullable nhận null khi đó là hành vi cần kiểm tra.

## 8. Đọc response bằng path()

Sau execute(), GraphQlTester trả về Response spec. Dùng path(...) để chọn một phần dữ liệu cần kiểm tra.

Ví dụ:

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Đường dẫn JsonPath mặc định tính tương đối từ phần data của GraphQL response. Vì vậy, không cần thêm prefix data.

Với response:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

Path đúng là bookById.id hoặc bookById.title, không phải data.bookById.id.

Có thể kiểm tra nhiều field trên cùng response bằng cách gọi path nhiều lần:

~~~java
GraphQlTester.Response response =
        graphQlTester.document(query)
                .variable("id", "b-01")
                .execute();

response.path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");

response.path("bookById.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
~~~

Cách này tránh thực thi cùng một query nhiều lần chỉ để kiểm tra các field khác nhau.

## 9. Kiểm tra scalar, object và list

### Scalar

Dùng entity(Class) khi path trỏ tới một giá trị scalar:

~~~java
graphQlTester.document("{ greeting }")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, Spring!");
~~~

### Object

Dùng entity(Class) để decode object thành DTO hoặc record:

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .path("bookById")
        .entity(Book.class)
        .satisfies(book -> {
            assertThat(book.id()).isEqualTo("b-01");
            assertThat(book.title())
                    .isEqualTo("GraphQL in Practice");
        });
~~~

Chỉ các field được query yêu cầu mới xuất hiện trong response. DTO dùng để decode cần tương thích với cấu trúc field đã chọn.

### List

Dùng entityList(Class) khi path trả về mảng:

~~~java
graphQlTester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
        .execute()
        .path("books")
        .entityList(Book.class)
        .hasSizeGreaterThan(0);
~~~

Có thể chọn field trong từng phần tử bằng JsonPath wildcard:

~~~java
graphQlTester.document("""
        query {
            books {
                title
            }
        }
        """)
        .execute()
        .path("books[*].title")
        .entityList(String.class)
        .contains("GraphQL in Practice");
~~~

Dùng wildcard khi muốn kiểm tra một thuộc tính trên toàn bộ phần tử mà không phụ thuộc thứ tự. Nếu thứ tự là một phần của hợp đồng API, hãy kiểm tra thứ tự một cách tường minh.

## 10. Kiểm tra JSON với matchesJson()

Khi muốn xác nhận cấu trúc của cả object hoặc list, matchesJson() giúp so sánh với JSON mong đợi.

Ví dụ:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "b-01") {
                id
                title
            }
        }
        """)
        .execute()
        .path("bookById")
        .matchesJson("""
                {
                    "id": "b-01",
                    "title": "GraphQL in Practice"
                }
                """);
~~~

matchesJson() phù hợp khi test cần xác nhận nhiều field cùng lúc. Với test chỉ quan tâm một giá trị, path(...).entity(...) thường ngắn và ít phụ thuộc cấu trúc không liên quan hơn.

matchesJson() cần thư viện JSONassert trên test classpath. Nếu project không dùng thư viện này, hãy dùng entity(), entityList() hoặc assertion theo từng path.

Không nên so sánh toàn bộ response nếu test chỉ quan tâm một phần nhỏ. Điều đó làm test dễ hỏng khi schema bổ sung field mới mà hành vi đang kiểm tra không đổi.

## 11. Kiểm tra nested path

Response có thể lồng nhiều object. Có thể gọi path() với callback để kiểm tra nhiều field tương đối từ một object cha.

Trong ví dụ mở rộng này, schema bổ sung quan hệ Author:

~~~graphql
extend type Book {
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Các ví dụ nested path, fragment và partial data bên dưới giả định test fixture có thể cung cấp Author cho Book, thông qua property có sẵn hoặc resolver Book.author.

Ví dụ query:

~~~graphql
query {
  bookById(id: "b-01") {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Test:

~~~java
graphQlTester.document("""
        query {
          bookById(id: "b-01") {
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
        .path("bookById", book -> book
                .path("id")
                .entity(String.class)
                .isEqualTo("b-01")
                .path("author.name")
                .entity(String.class)
                .isEqualTo("Nguyen An"));
~~~

Trong callback, các path con được tính tương đối từ object đã chọn. Điều này hữu ích khi response có cấu trúc sâu và test cần xác nhận nhiều field thuộc cùng một nhánh.

Có thể kết hợp path lồng nhau với entity() để decode một object con thành DTO riêng.

## 12. Tải query từ file bằng documentName()

Với query dài hoặc được tái sử dụng, nên lưu GraphQL document thành file trong test resources.

Ví dụ đường dẫn:

~~~text
src/test/resources/graphql-test/bookById.graphql
~~~

Nội dung:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
    publishedYear
  }
}
~~~

Test gọi document theo tên file:

~~~java
graphQlTester.documentName("bookById")
        .variable("id", "b-01")
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Mặc định, DocumentSource của GraphQlTester tìm file .graphql hoặc .gql trong classpath directory graphql-test/. Không cần ghi phần mở rộng file khi gọi documentName().

Đặt query trong file giúp:

- Test method tập trung vào variables và assertion.
- GraphQL document có thể được review độc lập.
- IDE hỗ trợ syntax highlight và completion.
- Operation có thể được dùng lại trong nhiều test.
- Query dài không làm test Java khó đọc.

Đừng nhầm thư mục graphql-test/ của GraphQlTester với graphql-documents/ thường dùng cho GraphQlClient trong code ứng dụng.

## 13. Tái sử dụng fragment trong test

GraphQL fragment cho phép chia sẻ field selection giữa nhiều operation.

Ví dụ file fragment:

~~~text
src/test/resources/graphql-test/authorFields.graphql
~~~

Nội dung:

~~~graphql
fragment authorFields on Author {
  id
  name
}
~~~

Query:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    author {
      ...authorFields
    }
  }
}
~~~

Lưu query trên vào src/test/resources/graphql-test/bookWithAuthor.graphql để documentName("bookWithAuthor") có thể tải đúng file.

Test ghép fragment từ file:

~~~java
graphQlTester.documentName("bookWithAuthor")
        .fragmentName("authorFields")
        .variable("id", "b-01")
        .execute()
        .path("bookById.author.name")
        .entity(String.class)
        .isEqualTo("Nguyen An");
~~~

GraphQlTester hỗ trợ fragment(...) để thêm fragment dạng chuỗi và fragmentName(...) để tải fragment qua DocumentSource.

Fragment không làm thay đổi ý nghĩa của field được chọn. GraphQL server vẫn validate fragment type condition và các field bên trong fragment theo schema.

## 14. Execute và xử lý GraphQL errors

GraphQL response có thể chứa data và errors cùng lúc. Vì vậy, test cần xác định rõ lỗi nào là ngoài dự kiến và lỗi nào là hành vi đang được kiểm tra.

Khi gọi verify(), các errors chưa được lọc trong response sẽ làm assertion thất bại.

Ví dụ kiểm tra một field không phát sinh lỗi:

~~~java
graphQlTester.document("""
        query {
          bookById(id: "b-01") {
            id
            title
          }
        }
        """)
        .execute()
        .errors()
        .verify();
~~~

Nếu muốn xác nhận một lỗi cụ thể tồn tại, dùng expect(...):

Ví dụ dưới đây giả định resolver hoặc service ném lỗi BookNotFoundException khi ID không tồn tại và ứng dụng đã ánh xạ exception đó thành GraphQL error có message tương ứng.

~~~java
graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
                title
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                error.getMessage().contains("Book was not found"))
        .verify();
~~~

expect(...) làm test thất bại nếu không tìm thấy error phù hợp.

Nếu một lỗi đã được dự kiến và muốn tiếp tục kiểm tra data, có thể dùng filter(...):

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .errors()
        .filter(error ->
                error.getMessage().contains("Title unavailable"))
        .verify()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Chỉ lọc lỗi mà test thực sự mong đợi. Không lọc tất cả errors để làm test xanh vì điều đó có thể che giấu lỗi resolver hoặc lỗi schema.

Dùng satisfy(...) khi cần kiểm tra toàn bộ danh sách errors bằng assertion library:

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .errors()
        .satisfy(errors ->
                assertThat(errors)
                        .anyMatch(error ->
                                error.getMessage()
                                        .contains("Title unavailable")));
~~~

satisfy(...) cho phép kiểm tra errors như một nhóm và đánh dấu chúng đã được xử lý để test có thể tiếp tục kiểm tra response data nếu cần.

## 15. execute() và executeAndVerify() khác nhau thế nào?

Hai method phục vụ hai mục đích:

| Method | Kết quả | Khi nên dùng |
|---|---|---|
| execute() | Trả GraphQlTester.Response để đọc data và errors | Query cần kiểm tra field hoặc response |
| executeAndVerify() | Thực thi và xác nhận response không có errors | Chỉ cần xác nhận operation không có GraphQL errors |

Ví dụ dùng execute():

~~~java
graphQlTester.document("""
        query {
            bookById(id: "b-01") {
                title
            }
        }
        """)
        .execute()
        .path("bookById.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
~~~

Ví dụ dùng executeAndVerify():

~~~java
graphQlTester.document("""
        mutation {
            clearTestCache
        }
        """)
        .executeAndVerify();
~~~

executeAndVerify() không thay thế assertion về giá trị trả về. Nếu cần xác nhận mutation trả về true, số lượng bản ghi hoặc object mới, hãy dùng execute() rồi kiểm tra path tương ứng.

Với HTTP-based tester, execute() và executeAndVerify() có thể báo assertion failure nếu HTTP status không phải 200 theo hợp đồng GraphQlTester. Nếu cần kiểm tra status 4xx/5xx hoặc content negotiation ở tầng HTTP, dùng WebTestClient để xác nhận transport response riêng.

## 16. Phân biệt request error và field execution error

GraphQL có thể từ chối operation trước khi resolver chạy hoặc tạo lỗi trong quá trình resolve field.

| Loại lỗi | Thời điểm | Ví dụ |
|---|---|---|
| Parse error | Parse document | Thiếu dấu ngoặc hoặc cú pháp sai |
| Validation error | Kiểm tra theo schema | Query field không tồn tại |
| Variable coercion error | Coercion variables | Truyền chuỗi cho biến Int |
| Field execution error | Resolver thực thi | Service ném exception |
| Serialization error | Tạo response | Custom scalar không serialize được |

Request error thường khiến GraphQL không tạo phần data thực thi thông thường. Field execution error có thể tạo response partial với cả data và errors.

Ví dụ field execution error:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-01",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Unable to load title",
      "path": ["bookById", "title"]
    }
  ]
}
~~~

Khi test lỗi, cần kiểm tra message hoặc error code, path và tác động lên data theo nullability. Chỉ kiểm tra danh sách errors không rỗng thường chưa đủ để xác nhận API trả đúng hợp đồng.

## 17. Kiểm tra partial data cùng errors

Một field có thể lỗi trong khi các field khác vẫn trả dữ liệu. Đây là hành vi quan trọng của GraphQL.

Ví dụ query:

~~~graphql
query {
  bookById(id: "b-01") {
    id
    title
    author {
      name
    }
  }
}
~~~

Giả sử author resolver gặp lỗi nhưng Book vẫn có thể trả id và title. Test có thể kiểm tra lỗi cùng data:

~~~java
graphQlTester.document("""
        query {
          bookById(id: "b-01") {
            id
            title
            author {
              name
            }
          }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors ->
                assertThat(errors)
                        .anyMatch(error ->
                                error.getPath().contains("author")))
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Hãy thiết kế assertion theo nullability trong SDL. Nếu field author nullable, lỗi ở author có thể chỉ làm author thành null. Nếu một field non-null phát sinh null, GraphQL có thể đẩy null lên parent gần nhất cho phép null.

Không nên giả định mọi field error đều làm toàn bộ data trở thành null.

## 18. Kiểm thử khi Query không tìm thấy dữ liệu

Với field nullable, service có thể trả null khi không tìm thấy object. Test cần xác nhận response có null và không có error nếu đây là hợp đồng API.

Ví dụ:

~~~java
@Test
void shouldReturnNullWhenBookDoesNotExist() {
    when(bookService.findById("missing"))
            .thenReturn(null);

    graphQlTester.document("""
            query {
                bookById(id: "missing") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("bookById")
            .valueIsNull();

    verify(bookService).findById("missing");
}
~~~

Nếu field được khai báo non-null trong SDL, hành vi trả null sẽ khác: GraphQL tạo execution error và áp dụng null propagation. Test cần xác nhận đúng schema contract thay vì chỉ kiểm tra Java service trả null.

Khi test không tìm thấy dữ liệu, hãy phân biệt rõ:

- Không có dữ liệu là kết quả nghiệp vụ hợp lệ.
- Resolver phát lỗi vì không tìm thấy dữ liệu.
- Request không hợp lệ nên resolver không được gọi.

Ba trường hợp có thể tạo response khác nhau và cần test riêng nếu API hỗ trợ.

## 19. Dùng GraphQlTester cho full integration test

@GraphQlTest phù hợp với controller slice test. Khi muốn xác nhận toàn bộ ứng dụng, có thể dùng @SpringBootTest và HttpGraphQlTester.

Ví dụ:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class GraphQlHttpIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void shouldExecuteBookQueryThroughHttp() {
        graphQlTester.document("""
                query {
                    bookById(id: "b-01") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("bookById.id")
                .entity(String.class)
                .isEqualTo("b-01");
    }
}
~~~

Với test này:

- Ứng dụng Spring Boot được khởi động.
- HTTP endpoint GraphQL được gọi qua transport thật.
- Các thành phần web, security filter và GraphQL infrastructure có thể tham gia.
- Tester kiểm tra response từ server đang chạy.

Với Spring Boot 4, AutoConfigureHttpGraphQlTester thuộc package org.springframework.boot.graphql.test.autoconfigure.tester. Với Spring Boot 3, package thuộc org.springframework.boot.test.autoconfigure.graphql.tester.

Nếu chỉ cần kiểm tra HTTP handler trong mock web environment, có thể cấu hình tester với web test client tương ứng. Không cần khởi động server thật cho mọi test; chọn full integration test khi transport hoặc cấu hình web là một phần hành vi cần xác nhận.

## 20. Kiểm thử timeout và response bất đồng bộ

GraphQlTester có response timeout để tránh test chờ vô hạn khi operation không hoàn tất. Builder cho phép tùy chỉnh timeout phù hợp với test:

~~~java
GraphQlTester tester = GraphQlTester.builder(transport)
        .responseTimeout(Duration.ofSeconds(10))
        .build();
~~~

Ví dụ trên minh họa cấu hình cho tester được tạo từ GraphQlTransport. Với tester do Spring Boot auto-configure, có thể dùng mutate() để tạo tester mới với cấu hình thay đổi nếu builder của transport hỗ trợ.

Không tăng timeout để che giấu resolver chậm. Hãy phân biệt test chậm do môi trường với operation thực sự bị treo hoặc gọi downstream quá lâu.

Với reactive controller, GraphQlTester chờ GraphQL response hoàn tất. Không cần gọi subscribe() thủ công trong test để kích hoạt resolver. Hãy để tester thực thi request và quản lý việc thu kết quả.

## 21. Kiểm thử subscription khác Query

Query trả về một response cho mỗi operation. Subscription tạo một luồng response theo event, vì vậy dùng executeSubscription() thay cho execute().

Ví dụ:

~~~java
Flux<String> greetings = graphQlTester.document(
                "subscription { greetings }")
        .executeSubscription()
        .toFlux("greetings", String.class);

StepVerifier.create(greetings)
        .expectNext("Hi")
        .expectNext("Bonjour")
        .expectNext("Hola")
        .verifyComplete();
~~~

executeSubscription() trả về subscription spec để chuyển luồng response thành Flux hoặc kiểm tra từng event. GraphQlTester hỗ trợ subscription với WebSocketGraphQlTester hoặc một số server-side extension như ExecutionGraphQlServiceTester và WebGraphQlTester.

Không dùng execute() cho subscription rồi mong đợi nhiều response. Query và Subscription có lifecycle khác nhau.

## 22. Các lỗi thường gặp khi execute query

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| GraphQlTester không được inject | Thiếu spring-graphql-test hoặc test auto-configuration | Kiểm tra dependency và annotation |
| Query trả null ngoài dự kiến | Sai field path, argument hoặc service fixture | Kiểm tra schema, document và mock setup |
| Path không tìm thấy | Path không đúng hoặc field không nằm trong data | Kiểm tra response JSON và dùng path tương đối data |
| Test thất bại vì errors | Resolver tạo error chưa được xử lý | Xem errors và dùng expect/filter/satisfy có chủ đích |
| @GraphQlTest không tìm thấy service | Slice test không scan service bean | Dùng @MockitoBean hoặc @Import |
| documentName không tìm thấy file | File không ở graphql-test/ hoặc sai tên | Kiểm tra classpath và extension |
| Fragment không được nhận diện | Chưa ghép fragment vào request | Dùng fragment() hoặc fragmentName() |
| HTTP tester báo assertion về status | HTTP response không phải 200 | Kiểm tra transport status bằng WebTestClient |
| Test phụ thuộc thứ tự dữ liệu | Assertion dựa vào vị trí list không ổn định | Kiểm tra theo ID hoặc điều kiện tập hợp |
| Test subscription chỉ nhận một response | Dùng execute() hoặc publisher kết thúc sớm | Dùng executeSubscription() và kiểm tra event source |

## 23. Checklist viết test Execute query

Trước khi hoàn thành test cho một Query:

- [ ] GraphQL document hợp lệ theo schema.
- [ ] Variables và operationName được truyền đúng.
- [ ] Query được thực thi bằng execute().
- [ ] Path được tính tương đối từ data.
- [ ] Scalar, object hoặc list được decode đúng kiểu.
- [ ] Assertion chỉ kiểm tra field liên quan đến hành vi cần xác nhận.
- [ ] GraphQL errors được kiểm tra, không bị bỏ qua vô ý.
- [ ] Partial data và null propagation được xác nhận khi cần.
- [ ] Trường hợp không tìm thấy dữ liệu có test riêng.
- [ ] Test xác nhận service nhận đúng arguments.
- [ ] Document file và fragment được tải đúng nếu dùng.
- [ ] Chọn slice test hay HTTP integration test theo phạm vi.
- [ ] Dùng executeSubscription() cho Subscription thay vì execute().
- [ ] Không gọi subscribe() thủ công để kích hoạt query test.

## Kết luận

GraphQlTester cung cấp workflow thống nhất để thực thi GraphQL query trong test. Test tạo request bằng document, truyền operation name và variables, gọi execute(), sau đó dùng JsonPath để chọn dữ liệu và ánh xạ thành Java object.

Khi kiểm tra response, cần xác nhận cả data lẫn errors. executeAndVerify() phù hợp khi chỉ cần bảo đảm response không có lỗi; execute() phù hợp khi cần kiểm tra field, list, partial data hoặc error path. Kết hợp @GraphQlTest cho controller slice test và HttpGraphQlTester cho HTTP integration test giúp xác nhận đúng tầng hành vi mà ứng dụng cần bảo vệ.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing and GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [GraphQlTester.Request API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Request.html)
- [Spring GraphQL Server Guide](https://spring.io/guides/gs/graphql-server)
