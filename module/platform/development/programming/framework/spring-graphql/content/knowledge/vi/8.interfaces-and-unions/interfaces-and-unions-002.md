# Object implements interface

Trong GraphQL, **interface** định nghĩa một contract gồm các field mà nhiều object type cùng cung cấp. Khi một object type khai báo `implements`, object đó cam kết có đầy đủ các field của interface với kiểu dữ liệu tương thích. Nhờ vậy, một field có thể trả về interface để client làm việc với nhiều loại object thông qua cùng một tập field chung, rồi dùng inline fragment để lấy thêm dữ liệu riêng của từng loại.

Ví dụ, một trang tìm kiếm có thể trả về sách hoặc bài viết. Cả hai đều có `id` và `title`, nhưng sách có `isbn`, còn bài viết có `url`. Ta khai báo interface `SearchResult`, sau đó cho `Book` và `Article` triển khai interface này.

```graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
    availableCopies: Int!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    url: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

`Book` và `Article` đều phải cung cấp `id` và `title` theo contract của `SearchResult`. Mỗi object vẫn có thể khai báo thêm field riêng. Field `Query.search` trả về list các giá trị thuộc interface, nên một kết quả có thể là `Book` hoặc `Article`.

## 1. Interface là contract của GraphQL

Interface trong SDL là một abstract output type. Nó mô tả những field mà mọi object type triển khai phải cung cấp. Interface không phải object type cụ thể và không thể được trả về như một instance độc lập; khi thực thi, mỗi giá trị thực tế phải tương ứng với một object type cụ thể.

Ví dụ đơn giản:

```graphql
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
```

`Node` công bố field `id`. Cả `Book` và `Author` đều có thể được dùng ở nơi schema yêu cầu `Node`, chẳng hạn một query trả về `Node`:

```graphql
type Query {
    node(id: ID!): Node
}
```

Điều này cho phép client truy vấn `id` mà không cần biết object thực tế là sách hay tác giả. Nếu cần field riêng như `title` hoặc `name`, client dùng fragment có điều kiện theo object type.

Interface GraphQL là contract ở tầng API. Java class có thể dùng Java interface để chia sẻ hành vi hoặc kiểu dữ liệu, nhưng GraphQL interface và Java interface là hai khái niệm khác nhau. Bạn có thể dùng Java interface để mô hình hóa các giá trị trả về, nhưng GraphQL không tự suy ra toàn bộ schema từ Java interface; SDL vẫn phải khai báo interface và quan hệ `implements`.

## 2. Cú pháp `implements`

Một object type khai báo interface mà nó triển khai ngay sau tên type:

```graphql
type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
}
```

Một object có thể triển khai nhiều interface. Dùng dấu `&` để phân tách tên các interface:

```graphql
interface Node {
    id: ID!
}

interface Named {
    name: String!
}

type Author implements Node & Named {
    id: ID!
    name: String!
    biography: String
}
```

Trong ví dụ, `Author` phải đáp ứng contract của cả `Node` và `Named`. Nó có thể có thêm `biography` vì object type được phép cung cấp các field không có trong interface.

Một interface cũng có thể triển khai interface khác. Khi dùng quan hệ kế thừa interface, object type cần đáp ứng contract của interface trực tiếp và các interface được kế thừa theo quy tắc của GraphQL type system. Khả năng này phụ thuộc vào phiên bản GraphQL Java được ứng dụng sử dụng; hãy bảo đảm phiên bản runtime hỗ trợ cú pháp và validation tương ứng.

## 3. Quy tắc tương thích khi triển khai interface

GraphQL kiểm tra object type có thực sự thỏa contract của interface hay không khi xây dựng schema. Những quy tắc quan trọng gồm:

| Quy tắc | Yêu cầu |
| --- | --- |
| Field bắt buộc | Object phải có tất cả field được khai báo trong interface |
| Kiểu output | Kiểu trả về của field object phải bằng hoặc là subtype hợp lệ của kiểu trả về trong interface |
| Argument của field | Các argument do interface khai báo phải có trong field tương ứng của object với tên và kiểu tương thích |
| Argument bổ sung | Object có thể thêm argument riêng nếu argument đó không bắt buộc đối với client cũ |
| Field riêng | Object được phép thêm field không xuất hiện trong interface |
| Nhiều interface | Object phải đáp ứng contract của tất cả interface mà nó khai báo triển khai |

### Field phải tồn tại và có kiểu tương thích

Nếu interface khai báo:

```graphql
interface Resource {
    id: ID!
    label: String!
}
```

Object triển khai phải có cả `id` và `label`:

```graphql
type Book implements Resource {
    id: ID!
    label: String!
    isbn: String
}
```

Nếu bỏ `label`, hoặc đổi kiểu thành `Int`, schema không thỏa contract. Object có thể cung cấp kiểu trả về cụ thể hơn khi kiểu đó là subtype hợp lệ, nhưng không thể làm kiểu output kém tương thích hơn.

### Nullability và covariance của output type

Kiểu trả về của field trên object có thể cụ thể hơn kiểu của interface. Một ví dụ phổ biến là interface khai báo kiểu nullable, trong khi object bảo đảm trả về giá trị non-null:

```graphql
interface SearchResult {
    title: String
}

type Book implements SearchResult {
    title: String!
    isbn: String!
}
```

`String!` là kiểu cụ thể hơn `String`: object cam kết trả về giá trị, trong khi contract chung chỉ yêu cầu một chuỗi có thể null. Chiều ngược lại không hợp lệ: nếu interface khai báo `title: String!`, object không thể triển khai bằng `title: String` vì như vậy object có thể trả null ở nơi client đã được hứa là luôn có giá trị.

Quy tắc tương tự áp dụng cho list và các kiểu output lồng nhau. Ví dụ, `[Book!]!` có thể là kiểu trả về cụ thể hơn `[SearchResult!]` nếu `Book` là object type triển khai `SearchResult` và các wrapper đáp ứng quy tắc subtype. Khi thiết kế schema, nên chọn nullability của interface theo mức bảo đảm chung mà tất cả object triển khai có thể đáp ứng.

### Argument phải giữ đúng contract

Nếu interface định nghĩa argument, object phải giữ argument đó với tên và kiểu tương thích:

```graphql
interface Searchable {
    search(keyword: String!): [SearchResult!]!
}

type Catalog implements Searchable {
    search(keyword: String!): [SearchResult!]!
    searchByCategory(category: ID!): [Book!]!
}
```

Object có thể thêm argument riêng như `category` trên một field riêng. Nếu muốn thêm argument vào chính field triển khai interface, argument bổ sung không được trở thành bắt buộc theo cách khiến client hợp lệ khi gọi qua interface lại không thể gọi object field.

Ví dụ sau không hợp lệ vì `locale` là argument bắt buộc mới mà interface không yêu cầu:

```graphql
interface Named {
    displayName: String!
}

type Author implements Named {
    displayName(locale: String!): String!
}
```

Client chỉ biết contract `Named.displayName` sẽ không biết phải cung cấp `locale`, trong khi resolver của object lại yêu cầu argument đó. Nếu argument bổ sung có giá trị mặc định hoặc nullable, nó không bắt buộc với client và có thể phù hợp với quy tắc implementation.

## 4. Interface field và field riêng của object

Khi client truy vấn qua một interface, client chỉ có thể chọn trực tiếp những field được khai báo trong interface. Các field riêng của object type phải được chọn bằng fragment.

Với schema `SearchResult`, query sau hợp lệ:

```graphql
query SearchCatalog {
    search(keyword: "Spring") {
        id
        title
        ... on Book {
            isbn
        }
        ... on Article {
            url
        }
    }
}
```

`id` và `title` là field chung nên được chọn trực tiếp. `isbn` chỉ có trên `Book`, còn `url` chỉ có trên `Article`, do đó cần inline fragment `... on Book` và `... on Article`.

Có thể dùng named fragment nếu selection set được tái sử dụng:

```graphql
fragment BookFields on Book {
    isbn
}

fragment ArticleFields on Article {
    url
}

query SearchCatalog {
    search(keyword: "GraphQL") {
        id
        title
        ...BookFields
        ...ArticleFields
    }
}
```

Nếu chọn `isbn` trực tiếp trên `SearchResult`, GraphQL validation sẽ báo field không tồn tại trên interface. Fragment cho phép client truy cập field riêng mà vẫn giữ query hợp lệ với nhiều kiểu object.

## 5. `__typename` và kiểu object thực tế

GraphQL cung cấp meta field `__typename` để client biết tên object type cụ thể tại runtime. Field này đặc biệt hữu ích khi query trả về interface hoặc union:

```graphql
query SearchCatalog {
    search(keyword: "Spring") {
        __typename
        id
        title
    }
}
```

Response có thể chứa nhiều kiểu object trong cùng một list:

```json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-01",
        "title": "Spring in Action"
      },
      {
        "__typename": "Article",
        "id": "article-02",
        "title": "GraphQL API Design"
      }
    ]
  }
}
```

Client có thể dùng `__typename` để chọn cách hiển thị hoặc giải mã dữ liệu. Tên trả về là tên object type trong GraphQL schema, không nhất thiết trùng với tên Java class.

## 6. Type resolution: GraphQL xác định object cụ thể như thế nào?

Interface là abstract type, nên khi resolver trả về một object cho field có kiểu interface, GraphQL Java cần biết object đó thuộc GraphQL object type nào. Quá trình này gọi là **type resolution**.

Type resolution khác với data fetching:

- `DataFetcher` lấy dữ liệu cho một field, ví dụ `Query.search` trả về danh sách kết quả.
- `TypeResolver` xác định kiểu GraphQL cụ thể cho từng object trong danh sách, ví dụ object Java `Book` tương ứng GraphQL type `Book`.
- Các field con sau đó được phân giải bằng resolver phù hợp hoặc property fetcher mặc định.

Nếu runtime không xác định được object type cụ thể, GraphQL không thể hoàn tất việc thực thi field trả về interface. Vì vậy, schema hợp lệ vẫn chưa đủ; ứng dụng phải cấu hình type resolution phù hợp với các loại object thực tế.

## 7. Tích hợp Object implements interface trong Spring for GraphQL

SDL khai báo interface và các object type triển khai. Controller có thể trả về một Java interface chung hoặc một kiểu cha phù hợp cho query:

```java
public interface SearchResult {
    String id();
    String title();
}

public record Book(
        String id,
        String title,
        String isbn) implements SearchResult {
}

public record Article(
        String id,
        String title,
        String url) implements SearchResult {
}
```

Resolver root trả về các object cụ thể:

```java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
```

`SearchService` có thể trả về danh sách gồm `Book` và `Article`. Tuy nhiên, việc khai báo Java interface `SearchResult` không tự động thay thế type resolver của GraphQL. Spring for GraphQL kết nối GraphQL Java với controller, còn GraphQL Java vẫn cần xác định object type cụ thể cho mỗi phần tử.

### Cấu hình TypeResolver qua RuntimeWiringConfigurer

Có thể cấu hình `TypeResolver` cho GraphQL interface bằng `RuntimeWiringConfigurer`:

```java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return builder -> builder.type("SearchResult", type ->
        type.typeResolver(environment -> {
            Object source = environment.getObject();

            if (source instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }

            if (source instanceof Article) {
                return environment.getSchema().getObjectType("Article");
            }

            throw new IllegalArgumentException(
                "Unsupported SearchResult type: " + source.getClass().getName());
        })
    );
}
```

Resolver đọc source object được trả về từ field cha và ánh xạ class Java sang `GraphQLObjectType` tương ứng. Khi thêm một loại kết quả mới, chẳng hạn `Video`, cần cập nhật schema, lớp dữ liệu và type resolution để runtime nhận diện được loại mới.

Với các dự án dùng quy ước tên Java class tương ứng tên GraphQL type, có thể cân nhắc `ClassNameTypeResolver` của Spring for GraphQL. Khi tên class và tên GraphQL type khác nhau hoặc mô hình domain phức tạp, một `TypeResolver` tường minh thường dễ kiểm soát hơn. Dù chọn cách nào, cần kiểm thử các loại object thực tế được trả về.

### Resolver cho field riêng của object

Field riêng của `Book` có thể dùng `@SchemaMapping`:

```java
@Controller
public class BookController {

    private final InventoryService inventoryService;

    public BookController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @SchemaMapping(typeName = "Book", field = "availableCopies")
    public int availableCopies(Book book) {
        return inventoryService.availableCopies(book.id());
    }
}
```

Nếu `isbn` là property có thể đọc trực tiếp từ record `Book`, GraphQL Java có thể dùng property fetcher mặc định và không cần resolver riêng. Dùng `@SchemaMapping` khi cần gọi service, chuyển đổi hoặc áp dụng logic nghiệp vụ. Field `url` của `Article` có thể được xử lý tương tự với `typeName = "Article"`.

## 8. Interface và DataLoader

Một field của interface có thể được triển khai bởi nhiều object type. Nếu field đó cần truy vấn dữ liệu liên quan, cách tối ưu vẫn giống các field thông thường: dùng `@BatchMapping` hoặc DataLoader để gom nhiều lần tải dữ liệu.

Ví dụ `SearchResult` có field `owner` trả về một interface `Node`:

```graphql
interface Node {
    id: ID!
}

interface SearchResult {
    id: ID!
    title: String!
    owner: Node
}

type Book implements SearchResult {
    id: ID!
    title: String!
    owner: Author
    isbn: String!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    owner: Author
    url: String!
}

type Author implements Node {
    id: ID!
    name: String!
}
```

Ở đây `Author` là object type triển khai `Node`, vì vậy `Book.owner` và `Article.owner` có thể trả về kiểu cụ thể `Author`, tương thích với kiểu `Node` trong interface. Nếu một query trả về nhiều kết quả và mỗi kết quả cần tải owner riêng, resolver có thể tạo ra N+1 truy vấn. Dùng DataLoader để gom các ID owner và truy vấn theo batch. Trong Spring for GraphQL, `BatchLoaderRegistry` và `@BatchMapping` là các cơ chế tích hợp cho mục tiêu này.

## 9. Kiểm thử object implementation và type resolution

Nên kiểm thử ít nhất ba lớp hành vi:

1. Schema validation: mọi object type triển khai interface có đủ field và kiểu tương thích.
2. Type resolution: từng class Java được ánh xạ sang đúng GraphQL object type.
3. Operation: client truy vấn field chung, `__typename` và field riêng qua inline fragment nhận được dữ liệu chính xác.

Ví dụ với `GraphQlTester`:

```java
graphQlTester.document("""
        query {
            search(keyword: "Spring") {
                __typename
                id
                title
                ... on Book {
                    isbn
                }
                ... on Article {
                    url
                }
            }
        }
        """)
    .execute()
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
```

Ngoài việc kiểm tra phần tử đầu tiên, nên kiểm tra trường hợp có đủ từng loại object trong danh sách, trường hợp danh sách rỗng và trường hợp service trả về một class chưa được type resolver hỗ trợ. Các trường hợp này giúp phát hiện lỗi mapping trước khi API được sử dụng bởi client.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Schema báo object chưa triển khai đủ interface | Thiếu field hoặc sai kiểu trả về | Bổ sung field và kiểm tra kiểu/nullability |
| Field interface có argument nhưng object thiếu | Chữ ký field không đáp ứng contract | Giữ đầy đủ argument theo tên và kiểu của interface |
| Object thêm required argument vào field triển khai | Client gọi qua interface không biết argument mới | Bỏ argument bắt buộc hoặc thiết kế field riêng |
| Object làm nullable field non-null của interface | Object không còn bảo đảm contract | Giữ non-null hoặc điều chỉnh interface nếu nghiệp vụ cho phép |
| Query không chọn được field riêng | Field không thuộc interface | Dùng inline fragment hoặc named fragment |
| Abstract type cannot be resolved | Không có TypeResolver phù hợp hoặc class chưa được ánh xạ | Cấu hình type resolver và xử lý mọi loại object |
| `__typename` không như mong đợi | Mapping class Java sang GraphQL type sai | Kiểm tra tên object type trả về từ resolver |
| Thêm interface field làm nhiều object lỗi | Các object triển khai interface chưa được cập nhật | Cập nhật toàn bộ implementation hoặc thu hẹp contract |

Khi schema không khởi động được, kiểm tra lỗi validation của quan hệ `implements`. Khi schema khởi động thành công nhưng query trả lỗi abstract type, kiểm tra `TypeResolver`. Nếu type đã được xác định nhưng field con sai dữ liệu, kiểm tra `DataFetcher`, `@SchemaMapping` và source object.

## 11. Nguyên tắc thiết kế interface

Chỉ đưa vào interface những field thực sự có ý nghĩa chung đối với tất cả object triển khai. Một field chỉ phù hợp với `Book` không nên được thêm vào interface `SearchResult` nếu `Article` không có cách cung cấp dữ liệu tương đương. Hãy giữ interface nhỏ và ổn định để client có thể dùng contract chung mà không phải hiểu mọi chi tiết của từng object.

Chọn nullability theo cam kết mà mọi implementation có thể đáp ứng. Tránh thêm argument bắt buộc vào field triển khai hoặc làm yếu kiểu output so với interface. Khi thêm field vào interface đang được nhiều object dùng, kiểm tra toàn bộ implementation và đánh giá ảnh hưởng đến client.

Trong Spring for GraphQL, giữ ranh giới rõ ràng giữa ba trách nhiệm: SDL mô tả interface và object contract; resolver lấy dữ liệu cho field; type resolver xác định object GraphQL cụ thể khi một field trả về interface. Khi ba phần này được cấu hình nhất quán, API có thể trả về nhiều loại object qua một field mà vẫn giữ schema rõ ràng và an toàn về kiểu dữ liệu.
