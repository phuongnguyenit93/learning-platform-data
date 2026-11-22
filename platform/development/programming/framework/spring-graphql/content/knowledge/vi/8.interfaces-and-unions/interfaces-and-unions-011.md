# Khi dùng interface hay union

GraphQL có hai abstract output type để mô tả một field có thể trả về nhiều object type cụ thể: **interface** và **union**. Cả hai đều cho phép client truy vấn dữ liệu đa hình, nhưng chúng thể hiện hai hợp đồng khác nhau. Interface định nghĩa một nhóm field chung mà mọi object triển khai phải cung cấp; union chỉ xác định tập object type có thể xuất hiện trong kết quả.

Chọn đúng loại giúp schema diễn đạt chính xác quan hệ giữa các kiểu dữ liệu, giúp client viết operation dễ hiểu và giúp server phân giải đúng object type tại runtime. Trong Spring for GraphQL, SDL khai báo interface/union, còn GraphQL Java cần xác định kiểu cụ thể của object trả về thông qua cơ chế type resolution phù hợp.

Bài này giải thích tiêu chí chọn interface hay union, cách client truy vấn bằng inline fragment và __typename, cách cấu hình runtime type resolver trong Spring for GraphQL, các lựa chọn thiết kế thay thế và cách kiểm thử.

## 1. Bài toán đa hình trong GraphQL

Giả sử API có một chức năng tìm kiếm trả về sách, tác giả hoặc nhà xuất bản. Mỗi loại kết quả có những field riêng:

~~~graphql
type Book {
  id: ID!
  title: String!
}

type Author {
  id: ID!
  name: String!
}

type Publisher {
  id: ID!
  companyName: String!
}
~~~

Nếu khai báo ba query riêng, client phải biết trước loại kết quả muốn tìm:

~~~graphql
type Query {
  books(term: String!): [Book!]!
  authors(term: String!): [Author!]!
  publishers(term: String!): [Publisher!]!
}
~~~

Thiết kế này hợp lý nếu ba use case thực sự độc lập. Nhưng nếu yêu cầu là tìm kiếm tổng hợp và một kết quả có thể thuộc bất kỳ loại nào, server cần một kiểu trả về thể hiện nhiều khả năng. Interface hoặc union giải quyết bài toán đó.

Client có thể truy vấn một field duy nhất:

~~~graphql
type Query {
  search(term: String!): [SearchResult!]!
}
~~~

Phần còn lại của schema sẽ định nghĩa **SearchResult** là union hoặc interface tùy vào mối quan hệ giữa các kiểu kết quả.

## 2. Interface: khi các object có hợp đồng field chung

Interface định nghĩa những field mà nhiều object type cam kết cung cấp. Ví dụ, sách và tác giả đều có định danh:

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

type Query {
  node(id: ID!): Node
}
~~~

**Node** khai báo field chung **id**. Mọi object triển khai interface phải cung cấp field này với kiểu tương thích. **Book** và **Author** vẫn là object type độc lập, có thể bổ sung field riêng của mình.

Client có thể truy vấn field chung trực tiếp trên interface:

~~~graphql
query {
  node(id: "item-01") {
    id
    __typename
  }
}
~~~

Nếu cần field riêng của một kiểu cụ thể, client dùng inline fragment:

~~~graphql
query {
  node(id: "item-01") {
    id
    ... on Book {
      title
    }
    ... on Author {
      name
    }
  }
}
~~~

Field **id** được truy vấn trực tiếp vì interface bảo đảm mọi kiểu triển khai đều có field đó. Field **title** và **name** chỉ được chọn trong fragment tương ứng.

### Interface nên đại diện cho một khái niệm chung

Một interface tốt thể hiện một hợp đồng có ý nghĩa với client, chẳng hạn:

- **Node**: các tài nguyên có định danh chung.
- **Auditable**: các object có thông tin tạo và cập nhật.
- **SearchableItem**: các kết quả có field chung phục vụ tìm kiếm.
- **PaymentMethod**: các phương thức thanh toán cùng có mã và tên hiển thị.

Không nên tạo interface chỉ vì hai object tình cờ có một field cùng tên. Hãy xem field đó có cùng ý nghĩa và quy tắc trên các kiểu hay không, và client có thực sự cần truy vấn nó như một phần của hợp đồng chung không.

Ví dụ interface thanh toán:

~~~graphql
interface PaymentMethod {
  id: ID!
  displayName: String!
}

type CardPayment implements PaymentMethod {
  id: ID!
  displayName: String!
  lastFourDigits: String!
}

type BankTransfer implements PaymentMethod {
  id: ID!
  displayName: String!
  bankName: String!
  accountReference: String!
}
~~~

Client có thể lấy **id** và **displayName** mà không cần biết phương thức cụ thể, sau đó chọn field riêng qua fragment khi cần.

## 3. Union: khi kết quả có nhiều loại object không có hợp đồng chung

Union xác định một tập các object type có thể xuất hiện trong kết quả. Khác với interface, union không khai báo field chung:

~~~graphql
union SearchResult = Book | Author | Publisher

type Query {
  search(term: String!): [SearchResult!]!
}
~~~

Client không thể truy vấn trực tiếp **id**, **title** hoặc **name** trên **SearchResult**, dù một vài thành viên có field cùng tên. Client phải dùng inline fragment:

~~~graphql
query Search($term: String!) {
  search(term: $term) {
    __typename
    ... on Book {
      id
      title
    }
    ... on Author {
      id
      name
    }
    ... on Publisher {
      id
      companyName
    }
  }
}
~~~

Union phù hợp khi các kết quả khác loại được gom vào cùng một use case nhưng không có một tập field chung đủ ý nghĩa để trở thành interface. Ví dụ kết quả tìm kiếm có thể là sách, tác giả hoặc nhà xuất bản; chúng đều là kết quả tìm kiếm nhưng không nhất thiết cùng một khái niệm domain ngoài use case đó.

### Union chỉ chứa object type

Các thành viên của union phải là object type. Không thể khai báo scalar, enum, input object, interface hoặc union khác làm thành viên:

~~~graphql
union InvalidResult = Book | String
~~~

Khai báo trên không hợp lệ vì **String** là scalar. Nếu một kết quả có thể là nhiều dạng dữ liệu, hãy bọc dữ liệu đó trong các object type riêng rồi đưa các object vào union.

## 4. Tiêu chí chọn interface hay union

Điểm quyết định không phải là số lượng kiểu cụ thể, mà là có tồn tại hợp đồng field chung có ý nghĩa hay không.

| Tiêu chí | Interface | Union |
|---|---|---|
| Mô tả | Hợp đồng field chung | Tập các object type có thể xuất hiện |
| Field truy vấn trực tiếp | Các field khai báo trên interface | Không có field chung do union khai báo |
| Field riêng của object | Dùng inline fragment | Dùng inline fragment |
| Thành viên | Object type triển khai interface | Object type được liệt kê trong union |
| Quan hệ giữa các kiểu | Có khả năng hoặc thuộc tính chung | Có thể hoàn toàn khác nhau |
| Ví dụ | PaymentMethod, Node | SearchResult, ActivityItem |
| Client cần biết kiểu cụ thể | Dùng __typename hoặc fragment | Thường dùng __typename và fragment |

Có thể dùng các câu hỏi sau để quyết định:

1. Các kiểu có một hoặc nhiều field chung mang cùng ý nghĩa nghiệp vụ không?
2. Client có cần truy vấn những field chung đó mà không viết fragment không?
3. Các object có thực sự cam kết cùng một khả năng, hay chỉ tình cờ xuất hiện trong cùng kết quả?
4. Khi thêm một kiểu mới, kiểu đó có thể thực hiện đầy đủ hợp đồng field chung không?
5. Client có cần phân biệt các kiểu cụ thể để hiển thị hoặc xử lý khác nhau không?

Nếu có hợp đồng chung rõ ràng và client cần sử dụng hợp đồng đó, interface thường phù hợp. Nếu chỉ cần diễn đạt “một trong các object type này”, union thường rõ nghĩa hơn.

### Ví dụ: cùng có id chưa chắc phải dùng interface

Giả sử kết quả tìm kiếm gồm **Book**, **Author** và **Publisher**. Cả ba đều có field **id**. Có thể tạo interface **Node** nếu API có khái niệm định danh tài nguyên thống nhất và client thường cần truy vấn ID chung.

Nếu **id** chỉ là một field kỹ thuật trùng tên, còn ba kiểu không có hành vi hoặc ý nghĩa chung nào khác, union **SearchResult** vẫn có thể là lựa chọn rõ ràng hơn. Khi dùng union, client truy vấn ID trong từng fragment. Không nên tạo interface chỉ để tránh lặp vài dòng SDL nếu hợp đồng chung không có giá trị với người dùng API.

### Có thể dùng cả interface và union trong cùng schema

Interface và union không loại trừ lẫn nhau. Một object type có thể triển khai interface và đồng thời là thành viên của một hoặc nhiều union:

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

union SearchResult = Book | Author

type Query {
  node(id: ID!): Node
  search(term: String!): [SearchResult!]!
}
~~~

Ở đây **Node** phục vụ các truy vấn cần định danh chung; **SearchResult** phục vụ use case tìm kiếm tổng hợp. Cùng một object type có thể tham gia cả hai hợp đồng.

## 5. Inline fragment và __typename

Interface và union là abstract type: một giá trị trả về thực tế luôn là một object type cụ thể. Client dùng inline fragment để chọn field theo kiểu đó.

Ví dụ:

~~~graphql
query {
  search(term: "spring") {
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

**__typename** là meta-field do GraphQL cung cấp. Nó trả về tên object type cụ thể tại runtime, chẳng hạn **Book** hoặc **Author**. Client thường dùng giá trị này để phân nhánh giao diện hoặc ánh xạ kết quả sang kiểu dữ liệu cụ thể.

Ví dụ response:

~~~json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-01",
        "title": "Spring GraphQL"
      },
      {
        "__typename": "Author",
        "id": "author-01",
        "name": "An Nguyen"
      }
    ]
  }
}
~~~

Với interface, field chung có thể được chọn ngoài fragment:

~~~graphql
query {
  searchableItems {
    id
    __typename
    ... on Book {
      title
    }
    ... on Author {
      name
    }
  }
}
~~~

Với union, không có field chung để chọn ngoài fragment:

~~~graphql
query {
  search(term: "spring") {
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

### Fragment có thể được đặt tên và tái sử dụng

Khi nhiều operation cần cùng selection set, client có thể khai báo fragment:

~~~graphql
fragment BookFields on Book {
  id
  title
}

fragment AuthorFields on Author {
  id
  name
}

query Search($term: String!) {
  search(term: $term) {
    __typename
    ...BookFields
    ...AuthorFields
  }
}
~~~

Fragment chỉ được áp dụng khi object runtime phù hợp với type condition. GraphQL bỏ qua fragment không khớp với object type cụ thể.

## 6. Runtime type resolution là gì?

Schema khai báo interface hoặc union chỉ mô tả những kiểu cụ thể có thể xuất hiện. Khi resolver trả về một Java object, GraphQL Java vẫn cần biết object đó tương ứng với object type nào trong schema.

Ví dụ resolver tìm kiếm trả về:

- Một instance Java của **Book**.
- Một instance Java của **Author**.
- Một instance Java của **Publisher**.

Field trong SDL có kiểu **SearchResult**, nhưng runtime phải xác định từng giá trị là **Book**, **Author** hay **Publisher**. Công việc đó gọi là **type resolution**.

Có thể hình dung luồng xử lý:

~~~mermaid
flowchart TD
    Q[Query.search resolver] --> L[Danh sách Java objects]
    L --> T{TypeResolver}
    T -->|Book instance| B[GraphQL object type Book]
    T -->|Author instance| A[GraphQL object type Author]
    T -->|Publisher instance| P[GraphQL object type Publisher]
    B --> F[Resolve fragment fields]
    A --> F
    P --> F
    F --> R[GraphQL response]
~~~

Nếu GraphQL không xác định được object type, operation có thể phát sinh execution error khi resolve abstract type. Vì vậy, khai báo union/interface trong SDL và trả về object Java đúng loại là hai phần cần được nối với nhau.

## 7. Cấu hình TypeResolver trong Spring for GraphQL

Spring for GraphQL sử dụng GraphQL Java runtime wiring. Có thể đăng ký **TypeResolver** cho interface hoặc union thông qua **RuntimeWiringConfigurer**.

Ví dụ schema:

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
  search(term: String!): [SearchResult!]!
}
~~~

Resolver trả về các object Java:

~~~java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<Object> search(@Argument String term) {
        return searchService.search(term);
    }
}
~~~

Runtime wiring có thể xác định object type từ kiểu Java:

~~~java
@Configuration
public class GraphQlTypeResolverConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> wiringBuilder.type(
                TypeRuntimeWiring.newTypeWiring("SearchResult")
                        .typeResolver(environment -> {
                            Object source = environment.getObject();

                            if (source instanceof Book) {
                                return environment.getSchema()
                                        .getObjectType("Book");
                            }
                            if (source instanceof Author) {
                                return environment.getSchema()
                                        .getObjectType("Author");
                            }

                            throw new IllegalStateException(
                                    "Unsupported SearchResult type: "
                                            + source.getClass().getName());
                        }));
    }
}
~~~

Trong ví dụ, **TypeRuntimeWiring** gắn type resolver với union **SearchResult**. Resolver đọc source object, kiểm tra kiểu Java và trả về **GraphQLObjectType** tương ứng trong schema.

Nếu field trả về interface, đăng ký type resolver cho tên interface theo cùng cách. Một object type có thể triển khai nhiều interface; mỗi abstract type cần có cách xác định kiểu cụ thể phù hợp.

Đây là ví dụ minh họa cho schema-first runtime wiring. Tên GraphQL type phải khớp với SDL, và các class Java cần thay bằng kiểu dữ liệu thực tế của ứng dụng. Nếu dùng cơ chế type resolution mặc định hoặc **isTypeOf** trên object type, có thể không cần một resolver tường minh; hãy kiểm tra hành vi runtime wiring của ứng dụng trước khi bổ sung cấu hình.

### Không nhầm TypeResolver với field resolver

Hai cơ chế có trách nhiệm khác nhau:

| Cơ chế | Trả lời câu hỏi |
|---|---|
| TypeResolver | Object Java này thuộc GraphQL object type cụ thể nào? |
| DataFetcher / @SchemaMapping | Giá trị của field đang được truy vấn là gì? |

Ví dụ **TypeResolver** xác định source object là **Book**. Sau đó field resolver hoặc property data fetcher mới lấy **Book.title** hoặc field quan hệ khác.

Không nên đặt logic tải dữ liệu vào TypeResolver. Type resolver nên xác định loại object từ dữ liệu đã có, còn việc lấy dữ liệu thuộc trách nhiệm resolver hoặc service.

## 8. Field resolver trên các object triển khai interface

Sau khi GraphQL biết kiểu cụ thể, các field của object được resolve theo mapping tương ứng. Spring for GraphQL hỗ trợ **@SchemaMapping** để ánh xạ field cụ thể:

~~~graphql
interface SearchableItem {
  id: ID!
}

type Book implements SearchableItem {
  id: ID!
  title: String!
  author: Author
}

type Author implements SearchableItem {
  id: ID!
  name: String!
}
~~~

Controller có thể triển khai root field và field quan hệ:

~~~java
@Controller
public class CatalogController {

    private final CatalogService catalogService;
    private final AuthorService authorService;

    public CatalogController(
            CatalogService catalogService,
            AuthorService authorService) {
        this.catalogService = catalogService;
        this.authorService = authorService;
    }

    @QueryMapping
    public List<Object> searchableItems() {
        return catalogService.findSearchableItems();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Field **id** có thể được cung cấp từ property của source object nếu có getter phù hợp. Field **author** cần resolver riêng vì phải tải tác giả từ service.

Nếu nhiều Book cùng cần tải Author, resolver riêng cho từng source có thể gây N+1. Có thể dùng **@BatchMapping** hoặc DataLoader để gom việc tải dữ liệu. Việc chọn interface hay union không tự giải quyết N+1; đó là vấn đề ở chiến lược data fetching.

## 9. Khi không nên dùng interface hoặc union

Không phải mọi trường hợp có nhiều trạng thái đều cần abstract type.

### Dùng enum khi chỉ cần biểu diễn trạng thái

Nếu một field chỉ có các giá trị phân loại đơn giản, enum thường phù hợp hơn:

~~~graphql
enum OrderStatus {
  NEW
  PROCESSING
  SHIPPED
  CANCELLED
}

type Order {
  id: ID!
  status: OrderStatus!
}
~~~

Không cần tạo union gồm các object **NewOrder**, **ShippedOrder** và **CancelledOrder** nếu các trạng thái chỉ khác nhau ở một giá trị enum và cùng một cấu trúc dữ liệu.

### Dùng object type thông thường khi cấu trúc ổn định

Nếu một field luôn trả về cùng một cấu trúc, dùng object type cụ thể:

~~~graphql
type Money {
  amount: Float!
  currency: String!
}

type Product {
  id: ID!
  price: Money!
}
~~~

Không cần union chỉ vì giá trị có nhiều currency. Currency là dữ liệu của object **Money**, không phải một object type khác nhau.

### Dùng wrapper object khi cần metadata chung

Đôi khi các kết quả khác loại không có field chung, nhưng API cần thêm thông tin về kết quả như điểm xếp hạng, nguồn dữ liệu hoặc thời điểm tìm thấy. Có thể bọc union trong một object:

~~~graphql
union SearchItem = Book | Author

type SearchHit {
  score: Float!
  source: String!
  item: SearchItem!
}

type Query {
  search(term: String!): [SearchHit!]!
}
~~~

Client có thể truy vấn metadata chung trên **SearchHit**, sau đó dùng fragment trên **item**:

~~~graphql
query {
  search(term: "spring") {
    score
    source
    item {
      __typename
      ... on Book {
        title
      }
      ... on Author {
        name
      }
    }
  }
}
~~~

Wrapper object hữu ích khi metadata thuộc về kết quả tìm kiếm chứ không thuộc về Book hoặc Author. Nó cũng tránh việc thêm các field không liên quan vào từng object type.

## 10. Interface và union chỉ dùng ở vị trí output

Interface và union là output type. Chúng có thể là kiểu trả về của field, nhưng không thể dùng làm kiểu argument hoặc field của input object.

Ví dụ sau không hợp lệ:

~~~graphql
input CreateActivityInput {
  target: SearchResult
}
~~~

Nếu client cần gửi một trong nhiều dạng dữ liệu, có thể dùng một trong các cách:

- Một input object có discriminator như **kind** và các field đầu vào tương ứng.
- Các mutation riêng cho từng loại hành động.
- Một input object chung chứa ID của tài nguyên đã tồn tại, sau đó server xác định kiểu từ dữ liệu.

Ví dụ input có discriminator:

~~~graphql
enum ActivityTargetKind {
  BOOK
  AUTHOR
}

input CreateActivityInput {
  targetKind: ActivityTargetKind!
  targetId: ID!
}

type Mutation {
  createActivity(input: CreateActivityInput!): Activity!
}
~~~

Server xác minh target ID và target kind có khớp với object thực tế hay không. Không được tin discriminator do client gửi mà bỏ qua kiểm tra quyền hoặc loại tài nguyên.

## 11. Schema evolution khi dùng interface và union

Abstract type tạo hợp đồng cho client, vì vậy việc thay đổi thành viên hoặc field có thể ảnh hưởng code sinh tự động và logic phân nhánh của client.

| Thay đổi | Ảnh hưởng cần cân nhắc |
|---|---|
| Thêm field vào interface | Mọi object triển khai phải cung cấp field tương thích; client có thể bắt đầu truy vấn field mới |
| Thêm object triển khai interface | Client có thể nhận kiểu mới; logic phân nhánh cần có nhánh dự phòng |
| Thêm thành viên vào union | Client có thể nhận object type mới và cần xử lý fragment tương ứng |
| Xóa thành viên khỏi union | Fragment và code client dành cho kiểu đó có thể trở nên không còn phù hợp |
| Đổi tên interface/union | Operation tham chiếu type condition hoặc field trả về có thể không còn hợp lệ |
| Thay đổi field chung | Có thể ảnh hưởng tất cả client truy vấn interface |

Khi thêm thành viên mới vào union, client không nên giả định danh sách kiểu là bất biến. Hãy dùng **__typename** và có nhánh xử lý fallback khi nhận kiểu chưa biết. Với client sinh code, kiểm tra cấu hình xử lý unknown type hoặc chiến lược cập nhật generated models.

Khi thêm field vào interface, tất cả object triển khai phải đáp ứng hợp đồng mới. Nếu các object không thể cung cấp field đó với cùng ý nghĩa, có thể field không nên nằm trên interface; hãy cân nhắc fragment trên kiểu cụ thể hoặc một interface nhỏ hơn.

## 12. Bảo mật với interface và union

Việc một object type triển khai interface hoặc là thành viên của union không tự cấp quyền truy cập cho người dùng. Authorization vẫn cần được kiểm tra trên từng object và field.

Ví dụ:

~~~graphql
interface Account {
  id: ID!
  displayName: String!
}

type PersonalAccount implements Account {
  id: ID!
  displayName: String!
  personalEmail: String
}

type BusinessAccount implements Account {
  id: ID!
  displayName: String!
  taxCode: String!
}
~~~

Một user có thể được phép xem **displayName** nhưng không được phép xem **personalEmail** hoặc **taxCode**. Resolver của các field nhạy cảm cần xác minh quyền phù hợp. Client dùng fragment chỉ để chọn field; fragment không phải cơ chế bảo mật.

Với union, mỗi thành viên có thể có chính sách bảo mật khác nhau. Server phải bảo đảm query trả về đúng object mà người dùng được phép nhìn thấy, đồng thời kiểm tra quyền cho các field con. Không nên chỉ kiểm tra quyền ở root search rồi mặc định mọi field trên kết quả đều công khai.

## 13. Kiểm thử interface và union

GraphQlTester có thể kiểm tra cả kiểu cụ thể lẫn field trong fragment. Ví dụ query:

~~~graphql
query Search($term: String!) {
  search(term: $term) {
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

Kiểm thử kiểu cụ thể:

~~~java
graphQlTester.document("""
        query {
            search(term: "spring") {
                __typename
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
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
~~~

Nên kiểm thử:

1. Resolver trả về đúng các loại Java object được khai báo trong interface/union.
2. TypeResolver ánh xạ từng object sang đúng GraphQL object type.
3. Unknown Java type được xử lý có chủ đích, không âm thầm trả sai kiểu.
4. Client truy vấn field chung của interface trực tiếp thành công.
5. Inline fragment chỉ trả field khi object type khớp.
6. Union không cho truy vấn field trực tiếp ngoài fragment, trừ meta-field được hỗ trợ.
7. **__typename** trả về đúng tên object type cụ thể.
8. Field resolver riêng của từng object type được gọi đúng.
9. Authorization được áp dụng cho field nhạy cảm trên từng thành viên.
10. Thêm thành viên mới không làm client hoặc mapping hiện tại xử lý sai.

Ngoài test execution, có thể kiểm tra schema khi ứng dụng khởi động để phát hiện object không triển khai đầy đủ interface hoặc union tham chiếu đến type không hợp lệ.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng union dù có hợp đồng field chung quan trọng | Client phải lặp fragment cho các field chung | Cân nhắc interface |
| Dùng interface chỉ vì field trùng tên | Hợp đồng chung không có ý nghĩa domain | Xác định cùng ngữ nghĩa trước khi tạo interface |
| Truy vấn field trực tiếp trên union | Operation không hợp lệ | Dùng inline fragment |
| Đưa scalar hoặc interface vào union | Schema không hợp lệ | Chỉ liệt kê object type |
| Khai báo interface nhưng không có type resolution phù hợp | Runtime không xác định được object cụ thể | Cấu hình TypeResolver hoặc cơ chế tương ứng |
| Nhầm TypeResolver với @SchemaMapping | Trộn lẫn xác định kiểu và tải field | Tách trách nhiệm hai cơ chế |
| Không xử lý kiểu mới ở client | UI hoặc generated client có thể lỗi khi thêm member | Dùng __typename và fallback |
| Đưa authorization vào fragment | Client có thể bỏ qua fragment và gọi field khác | Kiểm tra quyền ở server |
| Dùng abstract type cho dữ liệu đầu vào | SDL không hợp lệ | Thiết kế input object có discriminator hoặc mutation riêng |
| Dùng union để mô tả trạng thái đơn giản | Schema phức tạp không cần thiết | Dùng enum hoặc object thông thường |

## 15. Quy trình chọn interface hay union

Khi thiết kế một field có thể trả về nhiều kiểu object, hãy thực hiện:

1. Liệt kê các object type thực tế có thể xuất hiện.
2. Tìm các field chung và kiểm tra chúng có cùng ý nghĩa nghiệp vụ không.
3. Nếu có hợp đồng chung hữu ích cho client, định nghĩa interface.
4. Nếu chỉ cần tập các kiểu kết quả khác nhau, định nghĩa union.
5. Nếu chỉ biểu diễn trạng thái hoặc phân loại đơn giản, cân nhắc enum.
6. Nếu cần metadata chung cho kết quả đa hình, cân nhắc wrapper object chứa interface/union.
7. Thiết kế inline fragment và __typename cho client.
8. Cấu hình type resolution để map Java object sang GraphQL object type.
9. Giữ field resolver, authorization và batch loading ở đúng trách nhiệm.
10. Kiểm thử từng kiểu cụ thể và chuẩn bị cho việc thêm member trong tương lai.

Interface và union đều giúp GraphQL mô tả dữ liệu đa hình, nhưng mục đích của chúng khác nhau. Interface phù hợp khi các object chia sẻ một hợp đồng field có ý nghĩa; union phù hợp khi API cần trả về một trong nhiều object type mà không áp đặt field chung. Trong Spring for GraphQL, SDL định nghĩa hợp đồng, TypeResolver xác định kiểu cụ thể ở runtime và các resolver cung cấp giá trị field. Khi chọn theo ngữ nghĩa của dữ liệu và nhu cầu client, schema sẽ rõ ràng, dễ tiến hóa và dễ kiểm thử hơn.
