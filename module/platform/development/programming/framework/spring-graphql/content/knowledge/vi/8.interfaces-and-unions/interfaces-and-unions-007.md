# Union mapping trong controller với Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích GraphQL union biểu diễn một kết quả có thể thuộc nhiều object type như thế nào.
- Khai báo union và các object member trong SDL.
- Viết operation dùng inline fragment để lấy field theo kiểu kết quả.
- Trả về nhiều loại đối tượng khác nhau từ một method `@QueryMapping`.
- Hiểu vai trò của `TypeResolver` trong việc xác định GraphQL object type thực tế.
- Đăng ký mapping cho union bằng `RuntimeWiringConfigurer`.
- Dùng `ClassNameTypeResolver` hoặc resolver tùy chỉnh khi tên class Java khác tên type GraphQL.
- Kiểm thử union mapping và xử lý trường hợp server trả về kiểu không được khai báo.
- Phân biệt trách nhiệm của controller, resolver, union và các field mapping trên object member.

## 1. Union là gì?

GraphQL union là một abstract type cho phép một field trả về một trong nhiều object type đã được khai báo. Union hữu ích khi một kết quả tìm kiếm hoặc một danh sách có thể chứa các loại đối tượng khác nhau.

Ví dụ, chức năng tìm kiếm catalog có thể trả về sách hoặc tác giả:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}

union SearchResult = Book | Author

type Query {
    searchCatalog(keyword: String!): [SearchResult!]!
}
~~~

`SearchResult` là union gồm hai member là `Book` và `Author`. Field `searchCatalog` trả về danh sách kết quả; mỗi phần tử có thể là một `Book` hoặc một `Author`.

Union chỉ liệt kê các object type. Không thể khai báo một scalar, enum, input object, interface hoặc union khác làm member của union. Các member phải là object type hợp lệ trong schema.

Union không khai báo field chung như interface. Nó chỉ mô tả tập hợp những kiểu object mà kết quả có thể thuộc về. Vì vậy, client không thể chọn trực tiếp `id` hoặc `title` trên `SearchResult` nếu các field đó không được định nghĩa trên một interface chung.

## 2. Client truy vấn union bằng inline fragment

Vì union không có field nghiệp vụ riêng, client dùng inline fragment để chọn field theo object type cụ thể.

~~~graphql
query SearchCatalog {
    searchCatalog(keyword: "Spring") {
        __typename
        ... on Book {
            id
            title
        }
        ... on Author {
            id
            name
        }
    }
}
~~~

Ý nghĩa:

- `__typename` trả về tên GraphQL object type thực tế của từng phần tử.
- `... on Book` chỉ chọn các field thuộc `Book`.
- `... on Author` chỉ chọn các field thuộc `Author`.

Ví dụ response:

~~~json
{
    "data": {
        "searchCatalog": [
            {
                "__typename": "Book",
                "id": "book-42",
                "title": "Spring GraphQL"
            },
            {
                "__typename": "Author",
                "id": "author-12",
                "name": "An Nguyen"
            }
        ]
    }
}
~~~

Client có thể dựa vào `__typename` để quyết định cách hiển thị từng kết quả. Ví dụ, kết quả `Book` có thể dẫn đến trang chi tiết sách, còn `Author` dẫn đến trang hồ sơ tác giả.

Nếu operation chỉ yêu cầu field không tồn tại trên union, GraphQL validation sẽ từ chối operation:

~~~graphql
query {
    searchCatalog(keyword: "Spring") {
        id
    }
}
~~~

`id` có thể tồn tại trên cả `Book` và `Author`, nhưng union `SearchResult` không khai báo field đó. GraphQL không tự suy luận rằng mọi member tình cờ có field cùng tên đều tạo thành field chung. Hãy dùng inline fragment hoặc định nghĩa interface nếu cần một hợp đồng field chung.

## 3. Controller trả về nhiều loại đối tượng

Trong Spring for GraphQL, method được đánh dấu `@QueryMapping` có thể trả về một danh sách chứa nhiều loại object Java. Controller tập trung vào việc nhận argument và gọi service tìm kiếm.

Ví dụ các model kết quả:

~~~java
public record BookView(String id, String title) {
}

public record AuthorView(String id, String name) {
}
~~~

Service trả về các đối tượng thuộc những lớp khác nhau:

~~~java
@Service
class CatalogSearchService {

    List<Object> search(String keyword) {
        return List.of(
                new BookView("book-42", "Spring GraphQL"),
                new AuthorView("author-12", "An Nguyen")
        );
    }
}
~~~

Controller:

~~~java
@Controller
class CatalogController {

    private final CatalogSearchService searchService;

    CatalogController(CatalogSearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    List<Object> searchCatalog(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
~~~

`@QueryMapping` ánh xạ method `searchCatalog` với field cùng tên trên root type `Query`. Giá trị trả về là danh sách các source object. Mỗi source object cần được GraphQL runtime xác định thành một GraphQL object type thuộc union `SearchResult`.

Trong ví dụ, phần tử đầu tiên là `BookView` và phần tử thứ hai là `AuthorView`. Tên class Java khác tên GraphQL object type, nên cần có quy tắc ánh xạ rõ ràng.

Có thể dùng một interface Java chung thay cho `List<Object>` để thể hiện các kết quả thuộc cùng một nhóm trong domain:

~~~java
interface CatalogSearchItem {
}

public record BookView(String id, String title)
        implements CatalogSearchItem {
}

public record AuthorView(String id, String name)
        implements CatalogSearchItem {
}
~~~

Khi đó method controller có thể trả về `List<CatalogSearchItem>`. Interface Java giúp biểu diễn nhóm kết quả trong code, nhưng nó không tự động thay thế union trong GraphQL schema. GraphQL runtime vẫn cần xác định object type cụ thể cho từng phần tử.

## 4. TypeResolver xác định object type thực tế

GraphQL cần biết mỗi source object trong kết quả union tương ứng với GraphQL object type nào. Nhiệm vụ này thuộc về `TypeResolver`.

Khi thực thi một field trả về union:

1. Resolver của field, chẳng hạn method `@QueryMapping`, trả về một object hoặc danh sách object.
2. GraphQL runtime nhận source object của từng phần tử.
3. `TypeResolver` của union kiểm tra source object.
4. `TypeResolver` trả về `GraphQLObjectType` tương ứng, ví dụ `Book` hoặc `Author`.
5. GraphQL runtime dùng object type đó để thực thi selection set và các inline fragment phù hợp.

`TypeResolver` không tạo dữ liệu và không truy vấn database. Nó chỉ xác định kiểu GraphQL cụ thể của một source object đã được resolver trả về.

Nếu không thể xác định object type, GraphQL không thể hoàn tất việc thực thi union member. Vì vậy, mọi kiểu Java mà service có thể trả về cho union cần có mapping hợp lệ.

### 4.1. Quy tắc mapping theo tên class

Spring for GraphQL cung cấp `ClassNameTypeResolver` để suy ra GraphQL object type từ tên class Java. Cách này thuận tiện khi tên class Java và tên object type trong SDL tương ứng với nhau.

Ví dụ, source object thuộc class `Book` có thể được ánh xạ tới GraphQL object type `Book`. Nhưng trong ứng dụng thực tế, class Java thường mang hậu tố như `BookView`, `BookDto` hoặc `BookEntity` trong khi schema chỉ công bố `Book`.

Khi tên không trùng nhau, nên cấu hình mapping tường minh để không phụ thuộc vào quy ước đặt tên ngầm định.

### 4.2. Đăng ký ClassNameTypeResolver cho union

Ví dụ cấu hình mapping giữa DTO Java và GraphQL object type:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
class GraphQlUnionConfiguration {

    @Bean
    RuntimeWiringConfigurer unionTypeResolver() {
        ClassNameTypeResolver typeResolver =
                new ClassNameTypeResolver();

        typeResolver.addMapping(BookView.class, "Book");
        typeResolver.addMapping(AuthorView.class, "Author");

        return wiringBuilder ->
                wiringBuilder.type(
                        "SearchResult",
                        typeWiring -> typeWiring.typeResolver(typeResolver)
                );
    }
}
~~~

Trong cấu hình này:

- `ClassNameTypeResolver` là resolver hỗ trợ ánh xạ dựa trên class Java.
- `addMapping(BookView.class, "Book")` nói rõ source object `BookView` tương ứng với GraphQL type `Book`.
- `addMapping(AuthorView.class, "Author")` ánh xạ source object `AuthorView` thành GraphQL type `Author`.
- `RuntimeWiringConfigurer` đăng ký resolver cho abstract type có tên `SearchResult`.

Tên `SearchResult` phải khớp với union trong SDL. Các tên `Book` và `Author` phải khớp với object type được khai báo và liệt kê trong union.

Đăng ký mapping tường minh đặc biệt hữu ích khi dùng DTO, projection hoặc domain class có tên khác với GraphQL type. Nếu dùng tên class làm quy ước mặc định, hãy bảo đảm quy ước đó ổn định và không tạo ra xung đột giữa các lớp.

## 5. Tự viết TypeResolver khi cần quy tắc riêng

`ClassNameTypeResolver` phù hợp với mapping dựa trên class. Nếu ứng dụng cần quyết định kiểu theo một thuộc tính hoặc cấu trúc của source object, có thể viết `TypeResolver` trực tiếp.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
class CustomUnionConfiguration {

    @Bean
    RuntimeWiringConfigurer unionTypeResolver() {
        return wiringBuilder -> wiringBuilder.type(
                "SearchResult",
                typeWiring -> typeWiring.typeResolver(environment -> {
                    Object source = environment.getObject();

                    if (source == null) {
                        throw new IllegalStateException(
                                "SearchResult source must not be null"
                        );
                    }

                    if (source instanceof BookView) {
                        return environment.getSchema()
                                .getObjectType("Book");
                    }

                    if (source instanceof AuthorView) {
                        return environment.getSchema()
                                .getObjectType("Author");
                    }

                    throw new IllegalStateException(
                            "Unsupported SearchResult source type: "
                                    + source.getClass().getName()
                    );
                })
        );
    }
}
~~~

Trong ví dụ:

- `environment.getObject()` lấy source object đang được GraphQL runtime phân giải.
- `environment.getSchema().getObjectType("Book")` lấy object type `Book` từ schema hiện tại.
- Mỗi nhánh trả về đúng object type được union công bố.
- Kiểu source không được hỗ trợ sẽ tạo lỗi rõ ràng thay vì âm thầm chọn sai GraphQL type.

Nếu source object có thể null, hãy xử lý trường hợp đó một cách có chủ đích trước khi gọi `getClass()`. Thông thường, union member được khai báo non-null như `[SearchResult!]!` thì service không nên đưa phần tử null vào danh sách.

Nên ưu tiên `ClassNameTypeResolver` khi mapping chỉ dựa trên class. Chỉ dùng resolver tự viết khi có quy tắc phân loại cụ thể, ví dụ source object là một wrapper chung nhưng chứa discriminator xác định loại kết quả.

## 6. Một ví dụ hoàn chỉnh từ SDL đến controller

Kết hợp schema, DTO, service, controller và runtime wiring.

### 6.1. Schema SDL

~~~graphql
type Book {
    id: ID!
    title: String!
    publishedYear: Int
}

type Author {
    id: ID!
    name: String!
    biography: String
}

union SearchResult = Book | Author

type Query {
    searchCatalog(keyword: String!): [SearchResult!]!
}
~~~

`SearchResult` có hai member. Root field `searchCatalog` trả về danh sách không null và mỗi phần tử cũng không null.

### 6.2. DTO Java

~~~java
public record BookView(
        String id,
        String title,
        Integer publishedYear) {
}

public record AuthorView(
        String id,
        String name,
        String biography) {
}
~~~

DTO chỉ chứa dữ liệu cần thiết để GraphQL object type cung cấp. DTO có thể khác entity persistence để schema không bị ràng buộc trực tiếp với cấu trúc database.

### 6.3. Service tìm kiếm

~~~java
@Service
class CatalogSearchService {

    List<Object> search(String keyword) {
        // Ví dụ minh họa: kết quả có thể đến từ nhiều nguồn dữ liệu.
        return List.of(
                new BookView(
                        "book-42",
                        "Spring GraphQL",
                        2026
                ),
                new AuthorView(
                        "author-12",
                        "An Nguyen",
                        "Tác giả viết về Java và GraphQL"
                )
        );
    }
}
~~~

Trong ứng dụng thực tế, service sẽ tìm kiếm theo keyword, áp dụng quyền truy cập và trả về các DTO tương ứng. Ví dụ cố định chỉ tập trung thể hiện một danh sách có nhiều loại source object.

### 6.4. Controller

~~~java
@Controller
class CatalogController {

    private final CatalogSearchService searchService;

    CatalogController(CatalogSearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    List<Object> searchCatalog(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
~~~

Controller không cần tự tạo GraphQLObjectType hoặc tự viết response JSON. Nó trả về dữ liệu Java; GraphQL runtime và TypeResolver quyết định kiểu GraphQL của từng phần tử.

### 6.5. Runtime wiring

~~~java
@Configuration
class GraphQlUnionConfiguration {

    @Bean
    RuntimeWiringConfigurer unionTypeResolver() {
        ClassNameTypeResolver typeResolver =
                new ClassNameTypeResolver();

        typeResolver.addMapping(BookView.class, "Book");
        typeResolver.addMapping(AuthorView.class, "Author");

        return builder -> builder.type(
                "SearchResult",
                type -> type.typeResolver(typeResolver)
        );
    }
}
~~~

Sau khi cấu hình được nạp, GraphQL runtime có thể xác định:

| Source object Java | GraphQL object type |
| --- | --- |
| `BookView` | `Book` |
| `AuthorView` | `Author` |

Cấu hình union resolver được áp dụng cho abstract type `SearchResult`. Nếu schema có thêm union khác, mỗi union cần quy tắc mapping phù hợp với các member của nó.

### 6.6. Operation phía client

~~~graphql
query SearchCatalog($keyword: String!) {
    searchCatalog(keyword: $keyword) {
        __typename
        ... on Book {
            id
            title
            publishedYear
        }
        ... on Author {
            id
            name
            biography
        }
    }
}
~~~

Variables:

~~~json
{
    "keyword": "Spring"
}
~~~

Response có thể chứa các phần tử thuộc hai object type khác nhau:

~~~json
{
    "data": {
        "searchCatalog": [
            {
                "__typename": "Book",
                "id": "book-42",
                "title": "Spring GraphQL",
                "publishedYear": 2026
            },
            {
                "__typename": "Author",
                "id": "author-12",
                "name": "An Nguyen",
                "biography": "Tác giả viết về Java và GraphQL"
            }
        ]
    }
}
~~~

Client chỉ nhận field của inline fragment tương ứng với object type thực tế. Ví dụ phần tử `Book` không có field `biography` trong response.

## 7. Mapping field trên các union member

Union không có field riêng, nhưng các object type thành viên vẫn có field và resolver của chúng.

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}

type Author {
    id: ID!
    name: String!
}

union SearchResult = Book | Author

type Query {
    searchCatalog(keyword: String!): [SearchResult!]!
}
~~~

Khi client yêu cầu:

~~~graphql
query {
    searchCatalog(keyword: "Spring") {
        ... on Book {
            title
            author {
                name
            }
        }
        ... on Author {
            name
        }
    }
}
~~~

GraphQL thực hiện các field theo object type cụ thể:

- `Book.title` có thể lấy từ property của `BookView` hoặc resolver tương ứng.
- `Book.author` có thể được xử lý bởi `@SchemaMapping(typeName = "Book", field = "author")`.
- `Author.name` được resolve trên object type `Author`.

Ví dụ nested mapping:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    AuthorView author(BookView book) {
        return authorService.findByBookId(book.id());
    }
}
~~~

Union TypeResolver chỉ xác định một source object là `Book` hay `Author`. Sau khi xác định xong, GraphQL tiếp tục resolve các field được chọn trên object type đó bằng property access hoặc DataFetcher đã đăng ký.

Không viết một method `@SchemaMapping` cho chính union `SearchResult` để xử lý các field chung, vì union không định nghĩa field. Nếu nhiều member có cùng một nhóm field và client cần truy vấn trực tiếp các field chung đó, hãy cân nhắc dùng interface.

## 8. Khi nào nên dùng union và khi nào nên dùng interface?

Union và interface đều cho phép field trả về nhiều loại object, nhưng hợp đồng của chúng khác nhau.

| Tiêu chí | Union | Interface |
| --- | --- | --- |
| Mục đích | Gom các object type có thể xuất hiện trong cùng một kết quả | Định nghĩa tập field chung mà các object type triển khai |
| Khai báo field chung | Không có | Có |
| Client chọn field | Dùng inline fragment cho từng member | Có thể chọn field interface trực tiếp và dùng fragment cho field riêng |
| Thành viên | Các object type | Các object type triển khai interface |
| Ví dụ | `SearchResult = Book | Author` | `Node { id: ID! }` |

Dùng union khi các kết quả khác loại nhưng không có một hợp đồng field chung đủ ý nghĩa:

~~~graphql
union SearchResult = Book | Author | Publisher
~~~

Dùng interface khi mọi object type chia sẻ một nhóm field có cùng ngữ nghĩa:

~~~graphql
interface Node {
    id: ID!
}

type Book implements Node {
    id: ID!
    title: String!
}

type Author implements Node {
    id: ID!
    name: String!
}
~~~

Client có thể chọn trực tiếp `id` trên `Node` và dùng inline fragment cho các field riêng. Không nên tạo interface chỉ vì các object có field trùng tên nếu ý nghĩa hoặc quy tắc dữ liệu của chúng khác nhau.

## 9. Kiểm thử union mapping

Một test tích hợp nên xác minh cả kết quả trả về và `__typename` của từng phần tử. `GraphQlTester` có thể thực thi operation và kiểm tra response theo JSON path.

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query SearchCatalog($keyword: String!) {
            searchCatalog(keyword: $keyword) {
                __typename
                ... on Book {
                    id
                    title
                }
                ... on Author {
                    id
                    name
                }
            }
        }
        """)
        .variable("keyword", "Spring")
        .execute();

response.path("searchCatalog[0].__typename")
        .entity(String.class)
        .isEqualTo("Book");

response.path("searchCatalog[1].__typename")
        .entity(String.class)
        .isEqualTo("Author");
~~~

Test này xác minh TypeResolver ánh xạ đúng hai source object sang GraphQL object type tương ứng.

### 9.1. Kiểm thử field theo từng fragment

Ngoài `__typename`, cần xác minh các field của object type được resolve đúng:

~~~java
graphQlTester.document("""
        query {
            searchCatalog(keyword: "Spring") {
                ... on Book {
                    title
                }
                ... on Author {
                    name
                }
            }
        }
        """)
        .execute()
        .path("searchCatalog[0].title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Có thể tách thành nhiều test để dễ xác định nguyên nhân khi một member mapping sai.

### 9.2. Kiểm thử source object không được hỗ trợ

Nếu service trả về một class không có trong mapping, TypeResolver cần phát hiện tình huống đó. Test nên xác minh operation báo lỗi thay vì âm thầm phân loại object thành một type khác.

Các tình huống nên kiểm tra:

- Mỗi Java class được ánh xạ đúng GraphQL object type.
- Source object thuộc class không được hỗ trợ.
- Field của từng member được resolve đúng.
- Một member trả về null có phù hợp nullability của union field hay không.
- Inline fragment không khớp với member không làm lộ field của type khác.
- Resolver nested field của member hoạt động sau khi TypeResolver hoàn tất.

## 10. Lỗi thường gặp khi mapping union

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `Abstract type ... must resolve to an Object type` | TypeResolver không xác định được source object | Bổ sung mapping cho class Java |
| `Unknown type SearchResult` | SDL chưa khai báo union hoặc tên bị sai | Kiểm tra tên union trong SDL và runtime wiring |
| Object Java không được nhận diện | Tên class Java khác GraphQL object type | Dùng `ClassNameTypeResolver.addMapping` hoặc resolver riêng |
| Resolver trả class không thuộc union | Service trả về một kiểu ngoài các member đã khai báo | Chuẩn hóa kết quả hoặc cập nhật schema có chủ đích |
| Client không truy vấn được field trên union | Union không định nghĩa field chung | Dùng inline fragment hoặc chuyển sang interface khi phù hợp |
| `__typename` trả tên không mong đợi | Mapping trỏ đến object type sai | Kiểm tra mapping class-to-type |
| Nested field của member bị null hoặc lỗi | Chưa có DataFetcher/property phù hợp cho field đó | Kiểm tra `@SchemaMapping`, property và service |
| Thêm member mới nhưng query chưa xử lý | Client chưa có inline fragment cho type mới | Cập nhật client và kiểm tra fallback dựa trên `__typename` |

Một lỗi quan trọng là nhầm giữa mapping union và mapping field. TypeResolver chỉ trả lời câu hỏi "source object này là GraphQL type nào?". Nó không tự tải `author`, `reviews` hoặc các dữ liệu lồng nhau.

## 11. Quy trình triển khai union mapping

Khi xây dựng một field trả về nhiều loại object, có thể đi theo trình tự:

1. **Xác định các loại kết quả.** Liệt kê những object type thực sự có thể xuất hiện trong kết quả.
2. **Chọn union hay interface.** Dùng union khi không có field chung; dùng interface khi có hợp đồng chung.
3. **Khai báo SDL.** Tạo union từ các object type đã tồn tại và khai báo field trả về union.
4. **Thiết kế DTO/domain model.** Dùng các class hoặc record riêng cho từng loại kết quả.
5. **Viết controller.** Dùng `@QueryMapping` hoặc `@SchemaMapping` để trả về source object phù hợp.
6. **Cấu hình TypeResolver.** Ánh xạ từng class Java sang đúng GraphQL object type.
7. **Viết operation mẫu.** Dùng `__typename` và inline fragment để chọn field.
8. **Resolve nested field.** Bổ sung `@SchemaMapping` hoặc property access cho field của từng member.
9. **Kiểm thử.** Xác minh từng mapping, fragment, trường hợp không hỗ trợ và lỗi nullability.
10. **Tiến hóa schema.** Khi thêm member mới, kiểm tra resolver, client và các operation đang sử dụng union.

## 12. Tổng kết

Union cho phép một field GraphQL trả về nhiều object type khác nhau mà không cần ép chúng vào một cấu trúc field chung. Client dùng `__typename` và inline fragment để chọn dữ liệu theo object type thực tế. Trong Spring for GraphQL, controller có thể trả về danh sách các source object khác class; `TypeResolver` xác định từng object tương ứng với GraphQL object type nào.

`RuntimeWiringConfigurer` là nơi đăng ký resolver cho union. `ClassNameTypeResolver` phù hợp với mapping dựa trên tên class và hỗ trợ khai báo mapping tường minh cho DTO; resolver tự viết phù hợp khi cần quy tắc phân loại riêng. Sau khi union member được xác định, các field của member tiếp tục được resolve qua property access hoặc `@SchemaMapping`. Kiểm thử `__typename`, inline fragment và trường hợp source object không được hỗ trợ giúp bảo đảm union mapping hoạt động nhất quán từ service đến response.

