# Union type

## 1. Union type là gì?

Trong GraphQL, một field thường trả về một kiểu cụ thể như `Book`, `String` hoặc `[Order!]!`. Tuy nhiên, có những nghiệp vụ mà một field có thể trả về nhiều loại đối tượng khác nhau. Ví dụ, chức năng tìm kiếm toàn hệ thống có thể tìm thấy sách, tác giả hoặc nhà xuất bản. Khi đó, việc ép tất cả kết quả thành một object có nhiều field nullable thường làm schema khó hiểu và khiến client phải đoán loại kết quả.

GraphQL cung cấp **union type** để mô tả một giá trị có thể thuộc một trong nhiều object type đã xác định. Union là một abstract output type: nó gom các object type có thể không có quan hệ kế thừa hoặc không chia sẻ một tập field chung.

Ví dụ khai báo trong Schema Definition Language (SDL):

```graphql
union SearchResult = Book | Author | Publisher
```

`SearchResult` có thể đại diện cho một đối tượng `Book`, `Author` hoặc `Publisher`. Mỗi giá trị cụ thể tại thời điểm thực thi vẫn là một object type thực. GraphQL cần biết chính xác object type đó để kiểm tra selection set và trả về đúng các field.

Union thường được dùng làm kiểu trả về của field trong `Query`, `Mutation` hoặc `Subscription`. Union không phải object type và không thể được dùng làm root operation type.

## 2. Khai báo union trong SDL

### Cú pháp cơ bản

Union được khai báo bằng từ khóa `union`, tên union, dấu `=` và danh sách object type thành viên được ngăn cách bởi dấu `|`:

```graphql
union SearchResult = Book | Author | Publisher

type Book {
    id: ID!
    title: String!
    isbn: String
}

type Author {
    id: ID!
    name: String!
    penName: String
}

type Publisher {
    id: ID!
    companyName: String!
}
```

Các thành viên của union phải là **object type**. Không thể khai báo scalar, enum, input object hoặc một union khác làm thành viên. Mỗi thành viên cũng phải là một object type riêng biệt; không liệt kê trùng cùng một type.

Union không khai báo field bên trong thân type như object type. Cú pháp sau không hợp lệ:

```graphql
union SearchResult {
    id: ID!
    title: String
}
```

Nếu các loại kết quả có những field chung và API cần công bố một hợp đồng chung, hãy cân nhắc `interface`. Union phù hợp khi mục tiêu chính là biểu diễn một trong nhiều loại object khác nhau.

### Đưa union vào một field

Một field có thể trả về một union trực tiếp hoặc danh sách union:

```graphql
type Query {
    search(term: String!): [SearchResult!]!
    searchOne(id: ID!): SearchResult
}
```

Trong ví dụ:

- `search` luôn trả về một danh sách; từng phần tử trong danh sách phải là một object thuộc `SearchResult`.
- `searchOne` có thể trả về một object thuộc union hoặc `null` nếu không tìm thấy.
- `SearchResult` là output type, nên có thể xuất hiện trong kiểu trả về của field.

Union không phải input type. Không thể dùng union làm kiểu argument cho một field hoặc kiểu của biến đầu vào. Nếu client cần truyền một trong nhiều cấu trúc đầu vào, hãy thiết kế input object phù hợp hoặc dùng các field/operation riêng theo nghiệp vụ.

## 3. Ví dụ tìm kiếm trả về nhiều loại đối tượng

Giả sử ứng dụng thư viện cho phép tìm kiếm theo từ khóa. Kết quả có thể là sách, tác giả hoặc nhà xuất bản. Schema đầy đủ cho ví dụ:

```graphql
union SearchResult = Book | Author | Publisher

type Query {
    search(term: String!): [SearchResult!]!
}

type Book {
    id: ID!
    title: String!
    isbn: String
}

type Author {
    id: ID!
    name: String!
    penName: String
}

type Publisher {
    id: ID!
    companyName: String!
}
```

Khi client gọi `search`, mỗi phần tử trong danh sách có thể có hình dạng khác nhau. Một kết quả có thể là `Book` với `title`, kết quả khác là `Author` với `name`. Schema không yêu cầu các object này phải có cùng tập field.

Đây là lợi ích quan trọng của union: schema mô tả đúng sự đa dạng của dữ liệu, thay vì tạo một object tổng hợp như `SearchResult { book: Book, author: Author, publisher: Publisher }` trong đó phần lớn field thường xuyên là `null`.

## 4. Truy vấn union bằng inline fragment

Khi truy vấn một union, client không thể trực tiếp chọn các field riêng của từng object type vì union không định nghĩa field chung. Client cần dùng **inline fragment** để nói rõ field nào được chọn khi giá trị thực tế thuộc một kiểu cụ thể.

Ví dụ:

```graphql
query Search($term: String!) {
    search(term: $term) {
        __typename
        ... on Book {
            id
            title
            isbn
        }
        ... on Author {
            id
            name
            penName
        }
        ... on Publisher {
            id
            companyName
        }
    }
}
```

Ý nghĩa của các thành phần:

- `search(term: $term)` gọi field trả về danh sách union.
- `... on Book` chỉ chọn các field trong nhánh khi object thực tế là `Book`.
- `... on Author` chỉ chọn các field trong nhánh khi object thực tế là `Author`.
- `... on Publisher` chỉ chọn các field trong nhánh khi object thực tế là `Publisher`.
- `__typename` yêu cầu GraphQL trả về tên object type thực tế cho từng phần tử.

Nếu client viết trực tiếp `search { title }`, GraphQL sẽ từ chối vì `title` không phải field được khai báo trên union `SearchResult`. Field này chỉ tồn tại trên object type `Book`.

### Response minh họa

Giả sử server tìm thấy một quyển sách, một tác giả và một nhà xuất bản. Response có thể như sau:

```json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-101",
        "title": "GraphQL in Practice",
        "isbn": "9780000000001"
      },
      {
        "__typename": "Author",
        "id": "author-12",
        "name": "Nguyen An",
        "penName": null
      },
      {
        "__typename": "Publisher",
        "id": "publisher-8",
        "companyName": "Example Publishing"
      }
    ]
  }
}
```

Mỗi phần tử chỉ chứa field thuộc nhánh fragment phù hợp với kiểu thực tế. `__typename` cho biết chính xác object type mà server đã phân giải.

## 5. Vai trò của `__typename`

`__typename` là một GraphQL meta-field trả về tên object type cụ thể đang được thực thi. Với union, field này đặc biệt hữu ích vì client cần phân biệt các loại thành viên sau khi nhận dữ liệu.

Ví dụ, client có thể xử lý kết quả theo kiểu:

```javascript
switch (item.__typename) {
  case "Book":
    renderBook(item.title);
    break;
  case "Author":
    renderAuthor(item.name);
    break;
  case "Publisher":
    renderPublisher(item.companyName);
    break;
}
```

Trong JavaScript hoặc TypeScript, `__typename` thường được dùng làm discriminator để chọn giao diện hoặc nhánh xử lý tương ứng. Các công cụ sinh type từ GraphQL operation cũng có thể dựa vào field này để biểu diễn kết quả thành một discriminated union.

Không nên suy luận loại đối tượng từ sự tồn tại của một field tùy chọn, ví dụ `if (item.title)`. Field đó có thể vắng mặt hoặc có giá trị `null` theo dữ liệu và schema. `__typename` là tín hiệu rõ ràng do GraphQL cung cấp.

`__typename` có thể được chọn trực tiếp trên selection set của union. Những field riêng như `title`, `name` hoặc `companyName` vẫn phải nằm trong inline fragment hoặc named fragment tương ứng.

## 6. Dùng named fragment để tái sử dụng selection set

Khi cùng một nhóm field được dùng ở nhiều operation hoặc nhiều vị trí, client có thể khai báo **named fragment** trên từng object type:

```graphql
fragment BookSummary on Book {
    id
    title
    isbn
}

fragment AuthorSummary on Author {
    id
    name
}

query Search($term: String!) {
    search(term: $term) {
        __typename
        ...BookSummary
        ...AuthorSummary
        ... on Publisher {
            id
            companyName
        }
    }
}
```

`BookSummary` chỉ áp dụng cho `Book`, `AuthorSummary` chỉ áp dụng cho `Author`. GraphQL kiểm tra type condition của fragment để bảo đảm fragment chỉ được trải rộng trên object type phù hợp với vị trí sử dụng.

Named fragment giúp tránh lặp selection set và giữ các query lớn dễ đọc hơn. Tuy nhiên, fragment không thay đổi cấu trúc schema hoặc cách server xác định runtime type; nó chỉ là cơ chế tái sử dụng phần chọn field ở phía client.

## 7. Phân biệt Union type và Interface type

Union và interface đều là abstract output type, nhưng chúng thể hiện hai ý nghĩa khác nhau.

| Tiêu chí | Union | Interface |
| --- | --- | --- |
| Mục đích | Biểu diễn một trong nhiều object type | Định nghĩa hợp đồng field chung cho nhiều object type |
| Khai báo field chung | Không có field riêng | Có các field mà object triển khai phải đáp ứng |
| Thành viên | Chỉ object type | Object type triển khai interface |
| Truy vấn field | Dùng fragment để chọn field của từng object type | Có thể chọn trực tiếp field khai báo trên interface và dùng fragment cho field riêng |
| Quan hệ giữa các kiểu | Các object có thể không liên quan về cấu trúc | Các object chia sẻ một hợp đồng field |

Ví dụ interface:

```graphql
interface Node {
    id: ID!
}

type Query {
    nodes: [Node!]!
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

Với `Node`, client có thể truy vấn `id` trực tiếp vì đó là field chung được interface công bố:

```graphql
query {
    nodes {
        id
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

Nếu các kiểu kết quả chỉ cần được gom lại thành một tập lựa chọn, không có hợp đồng field chung, union thường phù hợp hơn. Nếu API cần bảo đảm mọi thành viên đều có một số field nhất định, interface diễn đạt hợp đồng đó tốt hơn.

## 8. Union type không phải input type

Union chỉ là output type. GraphQL không cho phép khai báo một argument hoặc input field có kiểu union:

```graphql
# Không hợp lệ: union không phải kiểu đầu vào
type Mutation {
    saveResult(value: SearchResult!): Boolean!
}
```

Nếu cần gửi một trong nhiều cấu trúc dữ liệu từ client lên server, có thể tạo input object với discriminator và các trường đầu vào phù hợp:

```graphql
enum SearchTargetKind {
    BOOK
    AUTHOR
}

input SearchTargetInput {
    kind: SearchTargetKind!
    bookId: ID
    authorId: ID
}

type Mutation {
    pinSearchTarget(input: SearchTargetInput!): Boolean!
}
```

Ở tầng nghiệp vụ, server cần kiểm tra tính nhất quán: nếu `kind` là `BOOK`, `bookId` phải có và `authorId` không được dùng; nếu `kind` là `AUTHOR`, quy tắc tương ứng được áp dụng. SDL cơ bản không tự diễn đạt được mọi ràng buộc phụ thuộc lẫn nhau giữa các field input, vì vậy cần validation trong ứng dụng.

Không nên nhầm giải pháp input object này với union. Nó là một cấu trúc input do ứng dụng định nghĩa để nhận dữ liệu từ client.

## 9. GraphQL cần xác định runtime type như thế nào?

Khi resolver của field trả về `SearchResult`, GraphQL biết giá trị thuộc một abstract type nhưng cần xác định object type cụ thể để tiếp tục thực thi fragment. Quá trình này gọi là **type resolution**.

Ví dụ resolver tìm kiếm trả về một danh sách đối tượng Java:

```java
public sealed interface SearchResult
        permits BookResult, AuthorResult, PublisherResult {
}

public record BookResult(String id, String title, String isbn)
        implements SearchResult {
}

public record AuthorResult(String id, String name, String penName)
        implements SearchResult {
}

public record PublisherResult(String id, String companyName)
        implements SearchResult {
}
```

Các class Java ở trên biểu diễn dữ liệu trả về từ service. Tên class Java không bắt buộc phải trùng với tên object type trong SDL, vì vậy server cần có quy tắc ánh xạ rõ ràng giữa chúng.

### Khai báo TypeResolver với Spring for GraphQL

Spring for GraphQL cho phép cấu hình GraphQL Java runtime wiring thông qua bean `RuntimeWiringConfigurer`. Với union `SearchResult`, có thể đăng ký một `TypeResolver` để trả về object type tương ứng với từng instance:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlTypeConfig {

    @Bean
    RuntimeWiringConfigurer searchResultTypeResolver() {
        return wiringBuilder -> wiringBuilder.type(
            "SearchResult",
            typeWiring -> typeWiring.typeResolver(environment -> {
                Object value = environment.getObject();

                if (value instanceof BookResult) {
                    return environment.getSchema().getObjectType("Book");
                }
                if (value instanceof AuthorResult) {
                    return environment.getSchema().getObjectType("Author");
                }
                if (value instanceof PublisherResult) {
                    return environment.getSchema().getObjectType("Publisher");
                }

                throw new IllegalStateException(
                    "Unsupported SearchResult type: " + value.getClass().getName()
                );
            })
        );
    }
}
```

`environment.getObject()` trả về giá trị Java mà data fetcher đã cung cấp. `TypeResolver` kiểm tra kiểu runtime rồi trả về `GraphQLObjectType` có tên tương ứng trong schema. Nếu resolver trả về một class không được hỗ trợ, ví dụ nên báo lỗi rõ ràng thay vì âm thầm chọn sai type.

Sau khi cấu hình type resolution, query resolver có thể trả về các implementation khác nhau:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search(@Argument String term) {
        return searchService.search(term);
    }
}
```

`SearchService` chịu trách nhiệm tìm kiếm và trả về các instance thuộc những class đã được đăng ký trong `TypeResolver`. Spring for GraphQL kết hợp data fetcher với runtime wiring để GraphQL engine biết cách xử lý từng phần tử của danh sách.

### Những điều cần kiểm tra khi type resolution thất bại

- Tên union trong `RuntimeWiringConfigurer` phải khớp chính xác với tên union trong SDL.
- Tên object type trả về phải tồn tại và là một thành viên của union.
- Data fetcher phải trả về đúng các class mà `TypeResolver` nhận diện.
- Mọi loại object có thể xuất hiện trong kết quả đều phải có nhánh phân giải.
- Không trả về `null` hoặc một object type không thuộc union cho một giá trị cần phân giải.

Nếu GraphQL không xác định được runtime type, query có thể phát sinh lỗi kiểu abstract type resolution dù SDL đã được parse thành công. Đây là lỗi ở bước thực thi, khác với lỗi cú pháp hoặc validation của schema.

## 10. Kết hợp union với phân trang và lọc

Union có thể được dùng trong danh sách có phân trang như các output type khác. Ví dụ:

```graphql
type SearchPage {
    items: [SearchResult!]!
    nextCursor: String
    hasNextPage: Boolean!
}

type Query {
    search(term: String!, first: Int = 20, after: String): SearchPage!
}
```

Client truy vấn các kết quả thuộc nhiều kiểu khác nhau trong từng trang:

```graphql
query SearchPage($term: String!, $first: Int!, $after: String) {
    search(term: $term, first: $first, after: $after) {
        nextCursor
        hasNextPage
        items {
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
}
```

Union không tự cung cấp cơ chế phân trang, sắp xếp hoặc lọc. Những hành vi đó được định nghĩa bằng arguments và output type của field bao quanh union. Server cần thống nhất thứ tự giữa các loại kết quả, cách tạo cursor và cách xử lý khi dữ liệu thay đổi trong lúc client duyệt các trang.

## 11. Lỗi thường gặp khi thiết kế và sử dụng union

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chọn field trực tiếp trên union | Union không khai báo field chung | Dùng inline fragment hoặc named fragment trên object type |
| Khai báo scalar hoặc interface làm thành viên | Union chỉ nhận object type | Tạo object type cụ thể hoặc cân nhắc interface nếu cần hợp đồng field chung |
| Dùng union làm argument hoặc input field | Union là output type | Tạo input object và validation nghiệp vụ |
| Không có `__typename` trong response | Client khó xác định loại object khi xử lý dữ liệu hỗn hợp | Chọn `__typename` trong selection set |
| Không cấu hình type resolution | GraphQL không biết instance Java tương ứng với object type nào | Đăng ký `TypeResolver` hoặc cơ chế ánh xạ phù hợp |
| TypeResolver trả về type không phải thành viên union | Runtime type không hợp lệ với schema | Kiểm tra mapping và tập thành viên SDL |
| Tạo một union quá rộng | Client phải xử lý nhiều loại không liên quan và schema khó tiến hóa | Chia union theo mục đích nghiệp vụ và phạm vi truy vấn |
| Dùng union khi mọi kiểu đều có field chung bắt buộc | Schema không thể thể hiện hợp đồng chung | Cân nhắc `interface` |

## 12. Kiểm thử union type

Nên kiểm tra cả schema, kết quả runtime và cách client nhận diện loại object.

**Kiểm tra SDL:** xác nhận mọi thành viên của union là object type tồn tại, không bị trùng và field trả về union được khai báo với nullability phù hợp.

**Kiểm tra validation của operation:** xác nhận field riêng chỉ được chọn bên trong fragment có type condition hợp lệ. Một operation chọn `title` trực tiếp trên `SearchResult` phải bị từ chối.

**Kiểm tra type resolution:** chuẩn bị ít nhất một instance cho mỗi object type thành viên và xác nhận `__typename` trong response lần lượt là `Book`, `Author` và `Publisher`. Đồng thời kiểm tra trường hợp service trả về một implementation không được hỗ trợ.

**Kiểm tra dữ liệu:** xác nhận các field đúng nhánh xuất hiện, field không thuộc nhánh không bị trả về, giá trị nullable được xử lý đúng và danh sách rỗng vẫn có response hợp lệ theo schema.

Với Spring GraphQL, có thể dùng `GraphQlTester` để gửi operation và kiểm tra response mà không cần kiểm thử từng resolver riêng lẻ. Ví dụ minh họa:

```java
graphQlTester.document("""
    query Search($term: String!) {
        search(term: $term) {
            __typename
            ... on Book { title }
            ... on Author { name }
            ... on Publisher { companyName }
        }
    }
    """)
    .variable("term", "spring")
    .execute()
    .path("search[0].__typename")
    .entity(String.class)
    .isEqualTo("Book");
```

Ví dụ giả định phần tử đầu tiên trong kết quả là `Book`. Trong bộ kiểm thử thực tế, nên kiểm tra đủ từng loại thành viên và không phụ thuộc vào thứ tự dữ liệu nếu service không cam kết thứ tự đó.

## 13. Checklist trước khi đưa union vào schema

- [ ] Union biểu diễn một tập object type có thể xuất hiện ở cùng một field.
- [ ] Các thành viên đều là object type hợp lệ và được khai báo trong schema.
- [ ] Field trả về union có nullability và cấu trúc danh sách rõ ràng.
- [ ] Client dùng inline fragment hoặc named fragment để chọn field riêng.
- [ ] Client chọn `__typename` nếu cần phân biệt kiểu runtime.
- [ ] Server có `TypeResolver` hoặc cơ chế ánh xạ runtime type phù hợp.
- [ ] Mọi class Java có thể được trả về đều được ánh xạ tới đúng object type trong union.
- [ ] Union không bị dùng làm input type hoặc root operation type.
- [ ] Đã cân nhắc interface nếu các object cần chia sẻ hợp đồng field chung.
- [ ] Có kiểm thử cho từng thành viên và trường hợp runtime type không hợp lệ.

## Kết luận

Union type cho phép một field GraphQL trả về một trong nhiều object type mà không buộc các object phải chia sẻ field chung. SDL khai báo tập thành viên bằng cú pháp `union Name = TypeA | TypeB`; client dùng inline fragment hoặc named fragment để chọn field theo từng kiểu cụ thể và dùng `__typename` để nhận diện kiểu runtime.

Trong Spring for GraphQL, data fetcher có thể trả về các instance Java thuộc nhiều class khác nhau. Server cần cấu hình type resolution để GraphQL engine ánh xạ từng instance tới object type tương ứng trong SDL. Chọn union khi cần mô tả một tập kết quả đa dạng; chọn interface khi API cần công bố một hợp đồng field chung. Thiết kế đúng giúp schema phản ánh rõ mô hình nghiệp vụ và giúp client xử lý dữ liệu hỗn hợp một cách an toàn.
