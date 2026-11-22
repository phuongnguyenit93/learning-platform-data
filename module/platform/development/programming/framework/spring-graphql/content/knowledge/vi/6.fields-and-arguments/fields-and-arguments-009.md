# Fragment

## 1. Fragment trong GraphQL là gì?

Khi một ứng dụng có nhiều màn hình cùng cần một nhóm field, các GraphQL operation thường lặp lại cùng một selection set. Ví dụ trang danh sách sách, trang tìm kiếm và trang chi tiết đều cần `id`, `title` và một phần thông tin tác giả. Nếu mỗi query tự khai báo lại các field này, tài liệu query sẽ dài, khó đồng bộ và dễ thiếu field khi schema thay đổi.

GraphQL cung cấp **fragment** để đặt tên cho một selection set có thể tái sử dụng. Client khai báo fragment một lần rồi trải rộng nó vào những vị trí phù hợp bằng fragment spread. Fragment giúp tổ chức query và dùng lại cấu trúc chọn field; nó không tạo thêm field trong schema, không thay thế resolver và cũng không phải một request độc lập.

Một named fragment có cú pháp cơ bản:

```graphql
fragment BookSummary on Book {
    id
    title
    publishedAt
}
```

Trong đó:

- `fragment` bắt đầu một định nghĩa fragment.
- `BookSummary` là tên fragment do client đặt.
- `on Book` là type condition: fragment chỉ áp dụng cho object type `Book`.
- Selection set bên trong `{ ... }` liệt kê những field cần lấy.

Khi dùng fragment trong operation, client viết `...BookSummary` tại vị trí có thể nhận kiểu `Book`:

```graphql
query BookCatalog {
    books {
        ...BookSummary
    }
}

fragment BookSummary on Book {
    id
    title
    publishedAt
}
```

GraphQL xử lý fragment spread như một phần của selection set tại vị trí sử dụng. Kết quả vẫn là một operation GraphQL bình thường, được gửi và thực thi qua endpoint GraphQL.

## 2. Fragment là thành phần của executable document

GraphQL có thể dùng SDL để định nghĩa schema và executable document để mô tả operation mà client muốn thực thi. `type`, `interface`, `union`, `input` và `enum` thuộc phần định nghĩa schema; `query`, `mutation`, `subscription`, fragment và selection set thuộc phần executable document.

Ví dụ schema:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    publishedAt: String
}
```

Ví dụ executable document sử dụng schema đó:

```graphql
query BookCatalog {
    books {
        ...BookSummary
    }
}

fragment BookSummary on Book {
    id
    title
    publishedAt
}
```

Fragment không được khai báo trong `schema.graphqls` như một object type. Nó được gửi cùng operation trong nội dung query. Phía server cần schema và resolver tương ứng để thực thi những field mà fragment yêu cầu.

## 3. Named fragment và fragment spread

### Khai báo và sử dụng named fragment

Named fragment là fragment có tên và có thể được sử dụng ở nhiều vị trí trong cùng một executable document. Ví dụ một màn hình cần danh sách sách cùng thông tin tác giả:

```graphql
fragment AuthorSummary on Author {
    id
    name
}

fragment BookSummary on Book {
    id
    title
    author {
        ...AuthorSummary
    }
}

query BookCatalog {
    books {
        ...BookSummary
    }
}
```

`BookSummary` chứa fragment spread `...AuthorSummary` bên trong field `author`. GraphQL kiểm tra type condition tại từng vị trí: `BookSummary` được dùng trong danh sách `Book`, còn `AuthorSummary` được dùng trong field có kiểu `Author`.

Một fragment có thể được trải rộng nhiều lần nếu type condition phù hợp:

```graphql
fragment BookIdentity on Book {
    id
    title
}

query CompareBooks($firstId: ID!, $secondId: ID!) {
    first: book(id: $firstId) {
        ...BookIdentity
    }
    second: book(id: $secondId) {
        ...BookIdentity
    }
}
```

Ở đây fragment được tái sử dụng cho hai field có cùng kiểu `Book`. Alias `first` và `second` đặt tên riêng cho hai kết quả trong response; fragment chỉ tái sử dụng selection set.

### Fragment spread có thể kết hợp nhiều fragment

Một selection set có thể trải rộng nhiều fragment:

```graphql
fragment BookIdentity on Book {
    id
    title
}

fragment BookPublication on Book {
    publishedAt
    isbn
}

query Books {
    books {
        ...BookIdentity
        ...BookPublication
    }
}
```

Kết quả cho mỗi phần tử có đủ các field từ hai fragment. Nếu các field cùng response key có cách gọi hoặc kiểu không tương thích, GraphQL validation có thể báo lỗi xung đột field. Vì vậy, việc tách fragment nên dựa trên các nhóm field có ý nghĩa và tránh tạo ra những selection set chồng chéo khó kiểm soát.

## 4. Inline fragment

Inline fragment là một selection set được viết trực tiếp tại nơi sử dụng, không cần khai báo tên riêng. Cú pháp thường gặp là `... on TypeName { ... }`.

Ví dụ, một kết quả tìm kiếm có thể là `Book` hoặc `Author`:

```graphql
union SearchResult = Book | Author

type Query {
    search(term: String!): [SearchResult!]!
}

type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
```

Client dùng inline fragment để chọn field theo object type thực tế:

```graphql
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
```

Nếu phần tử là `Book`, GraphQL thực thi nhánh `... on Book`; nếu là `Author`, GraphQL thực thi nhánh `... on Author`. `__typename` giúp client nhận biết object type cụ thể trong response.

Inline fragment cũng hữu ích với interface. Client có thể chọn field chung trực tiếp trên interface, sau đó chọn field riêng bằng type condition:

```graphql
interface Searchable {
    id: ID!
}

type Book implements Searchable {
    id: ID!
    title: String!
}

type Author implements Searchable {
    id: ID!
    name: String!
}

type Query {
    searchableItems: [Searchable!]!
}
```

Operation:

```graphql
query SearchableItems {
    searchableItems {
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

`id` được chọn trực tiếp vì nó thuộc interface `Searchable`. Các field `title` và `name` chỉ được chọn trong fragment có type condition tương ứng.

### Inline fragment không có type condition

GraphQL cũng cho phép inline fragment không ghi `on TypeName`. Dạng này nhóm các field và có thể gắn directive mà không thay đổi type condition:

```graphql
query BookDetails {
    book(id: "book-42") {
        id
        ... {
            title
            publishedAt
        }
    }
}
```

Inline fragment không có type condition giữ nguyên kiểu của vị trí chứa nó. Dạng có type condition thường dễ nhận biết hơn khi làm việc với interface hoặc union.

## 5. Fragment trên object, interface và union

Type condition quyết định fragment có thể được sử dụng ở đâu. GraphQL chỉ chấp nhận một fragment khi kiểu tại vị trí sử dụng có khả năng tương thích với type condition.

| Type condition | Cách sử dụng |
| --- | --- |
| Object type, ví dụ `Book` | Chọn field thuộc `Book` |
| Interface, ví dụ `Node` | Chọn field chung được interface công bố cho các object triển khai phù hợp |
| Union, ví dụ `SearchResult` | Chọn field theo từng object type thành viên bằng các fragment lồng bên trong |

Ví dụ fragment trên union:

```graphql
union SearchResult = Book | Author | Publisher

fragment SearchResultCard on SearchResult {
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

query Search($term: String!) {
    search(term: $term) {
        ...SearchResultCard
    }
}
```

Fragment `SearchResultCard` có type condition là union `SearchResult`. Bên trong fragment, các inline fragment xác định field cụ thể cho từng object type thành viên. Vì union không có field nghiệp vụ chung, `__typename` là meta-field có thể dùng để nhận diện kiểu runtime.

Ví dụ sai về type condition:

```graphql
query Search {
    search {
        ... on Order {
            id
            total
        }
    }
}
```

Nếu `Order` không phải thành viên của union `SearchResult` và không có khả năng xuất hiện tại vị trí này, GraphQL validation từ chối fragment vì các kiểu không thể giao nhau. Cần chọn type condition có quan hệ hợp lệ với kiểu tại vị trí fragment được trải rộng.

## 6. Sử dụng fragment với variables và arguments

Fragment không có danh sách arguments riêng như field hoặc function. Nếu fragment cần giá trị động, nó có thể tham chiếu đến variable được khai báo trong operation sử dụng fragment. Variable vẫn thuộc phạm vi của operation, không được khai báo bên trong fragment.

Ví dụ:

```graphql
fragment BookDetails on Book {
    id
    title
    author {
        id
        name
    }
}

query BookCatalog($first: Int!, $authorId: ID) {
    books(first: $first, authorId: $authorId) {
        ...BookDetails
    }
}
```

Schema minh họa:

```graphql
type Query {
    books(first: Int!, authorId: ID): [Book!]!
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
```

Request JSON:

```json
{
  "query": "fragment BookDetails on Book { id title author { id name } } query BookCatalog($first: Int!, $authorId: ID) { books(first: $first, authorId: $authorId) { ...BookDetails } }",
  "operationName": "BookCatalog",
  "variables": {
    "first": 20,
    "authorId": "author-7"
  }
}
```

Khi một fragment sử dụng variable trong field argument hoặc directive, operation sử dụng fragment phải khai báo variable đó với kiểu phù hợp. Nếu variable chưa được khai báo hoặc khai báo sai kiểu, GraphQL validation báo lỗi trước khi thực thi resolver.

## 7. Kết hợp fragment với directives

Directives cho phép điều khiển việc đưa một field hoặc fragment vào kết quả theo điều kiện. Hai directive chuẩn thường dùng là `@include(if: Boolean!)` và `@skip(if: Boolean!)`.

Ví dụ bật hoặc tắt phần chi tiết:

```graphql
fragment BookDetails on Book {
    isbn
    publishedAt
}

query BookCatalog($showDetails: Boolean!) {
    books {
        id
        title
        ...BookDetails @include(if: $showDetails)
    }
}
```

Khi `showDetails` là `true`, các field trong fragment được đưa vào kết quả; khi `false`, fragment spread bị bỏ qua. Với `@skip`, logic ngược lại được áp dụng.

Directive cũng có thể đặt trên inline fragment:

```graphql
query BookDetails($showPublication: Boolean!) {
    book(id: "book-42") {
        id
        title
        ... on Book @include(if: $showPublication) {
            publishedAt
            isbn
        }
    }
}
```

Các directive chuẩn chỉ ảnh hưởng đến selection set trong operation. Chúng không phải cơ chế phân quyền; server vẫn phải kiểm tra quyền truy cập trong resolver hoặc tầng nghiệp vụ cho mọi field được yêu cầu.

## 8. Quy tắc validation và các giới hạn của fragment

Fragment phải tuân thủ những quy tắc validation của executable document:

1. Tên fragment phải duy nhất trong document và không được đặt là `on`.
2. Type condition phải tham chiếu đến kiểu hợp lệ; fragment phải có khả năng áp dụng tại vị trí được spread.
3. Fragment spread phải tham chiếu đến một fragment đã được định nghĩa trong cùng document.
4. Các fragment không được tạo chu trình tham chiếu. Ví dụ A spread B và B spread lại A là không hợp lệ.
5. Fragment phải được sử dụng; fragment không được tham chiếu thường bị validation từ chối theo quy tắc unused fragments.
6. Mọi variable được tham chiếu trong fragment phải được khai báo trong operation sử dụng fragment và có kiểu tương thích.
7. Các field sau khi kết hợp fragment vẫn phải thỏa mãn quy tắc chọn field, argument, alias và kiểu dữ liệu của GraphQL.

Ví dụ chu trình không hợp lệ:

```graphql
fragment BookPart on Book {
    id
    ...AuthorPart
}

fragment AuthorPart on Book {
    title
    ...BookPart
}
```

Ví dụ này tạo vòng lặp giữa hai fragment. GraphQL không thể mở rộng selection set vô hạn, nên document bị từ chối.

Fragment cũng không phải là function có tham số. Không thể khai báo `fragment BookCard($showAuthor: Boolean!)`. Hãy dùng variable ở operation và directive ở fragment spread hoặc field nếu cần thay đổi lựa chọn theo điều kiện.

## 9. Fragment được thực thi như thế nào trên server?

Fragment là cách tổ chức executable document ở phía client. Khi server nhận request, GraphQL engine parse document, validate operation, mở rộng các fragment spread về mặt thực thi và tạo kế hoạch phân giải các field được chọn. Việc dùng fragment không tạo ra một resolver mới và không yêu cầu một endpoint riêng.

Với Spring for GraphQL, controller vẫn ánh xạ các field schema bằng `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping`. Resolver không cần biết field được yêu cầu trực tiếp hay thông qua fragment.

Ví dụ schema:

```graphql
type Query {
    books: [Book!]!
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
```

Controller minh họa:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

Client có thể gọi field `books` trực tiếp hoặc trải rộng fragment `BookSummary` tại field đó. Trong cả hai trường hợp, Spring for GraphQL phân giải cùng field schema và gọi cùng data fetcher. Nếu selection set yêu cầu `author`, field đó tiếp tục được phân giải theo cơ chế mapping tương ứng, chẳng hạn `@SchemaMapping` hoặc property access.

### Kiểm thử operation có fragment bằng GraphQlTester

`GraphQlTester` có thể gửi một document chứa cả operation và fragment:

```java
graphQlTester.document("""
    query BookCatalog {
        books {
            ...BookSummary
        }
    }

    fragment BookSummary on Book {
        id
        title
    }
    """)
    .execute()
    .path("books[0].title")
    .entity(String.class)
    .isEqualTo("GraphQL in Practice");
```

Đây là kiểm thử operation ở cấp GraphQL. Trong bộ kiểm thử thực tế, nên xác nhận cả fragment lồng nhau, field nullable, fragment không tương thích và trường hợp variable được dùng trong fragment.

## 10. Fragment, hiệu năng và khả năng bảo trì

Fragment giúp giảm lặp trong source query, nhưng bản thân fragment không làm giảm số field mà server phải phân giải. Nếu một fragment chứa nhiều field và được trải rộng vào operation, tất cả field được chọn vẫn là một phần của request thực thi.

Một số nguyên tắc sử dụng:

- Tạo fragment theo mục đích hiển thị hoặc nhóm field có ý nghĩa, chẳng hạn `BookCard`, `BookDetails` hoặc `AuthorSummary`.
- Giữ fragment đủ nhỏ để client dễ hiểu những dữ liệu mà nó yêu cầu.
- Dùng fragment lồng nhau có kiểm soát; tránh chuỗi fragment quá sâu khiến khó theo dõi selection set cuối cùng.
- Không gom mọi field của object vào một fragment lớn nếu màn hình chỉ cần một phần nhỏ.
- Tái sử dụng fragment giữa các operation có cùng nhu cầu dữ liệu và cùng type condition.
- Khi thay đổi schema, kiểm tra các fragment đang sử dụng field bị đổi tên hoặc deprecate.

GraphQL server vẫn cần đo chi phí query, giới hạn độ sâu/độ phức tạp khi cần và xử lý N+1 ở resolver. Việc tách query thành fragment không làm giảm độ phức tạp thực thi; ngược lại, một fragment lớn có thể khiến operation yêu cầu nhiều dữ liệu hơn dự kiến.

Fragment cũng có thể giúp client cache dữ liệu nhất quán hơn khi nhiều màn hình dùng cùng một cấu trúc field. Tuy nhiên, cơ chế cache normalized entity là tính năng của thư viện client; GraphQL specification không tự định nghĩa một cache client chung.

## 11. Các lỗi thường gặp khi dùng fragment

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Unknown fragment` | Fragment spread tham chiếu đến tên chưa định nghĩa hoặc fragment không nằm trong document gửi lên | Gửi cả fragment definition cùng operation và kiểm tra chính tả tên |
| Field không được phép chọn | Fragment có type condition không phù hợp hoặc field không tồn tại trên type đó | Đối chiếu schema và dùng type condition đúng |
| Fragment không được sử dụng | Fragment được định nghĩa nhưng không có fragment spread nào tham chiếu | Xóa fragment thừa hoặc thêm spread vào operation |
| Fragment cycle | Các fragment tham chiếu vòng lặp lẫn nhau | Tổ chức lại các fragment thành đồ thị không chu trình |
| Variable không được định nghĩa | Fragment sử dụng variable mà operation chứa spread không khai báo | Khai báo variable tại operation và truyền trong `variables` |
| Xung đột field | Các fragment tạo ra cùng response key với arguments hoặc kiểu không tương thích | Kiểm tra alias, arguments và cấu trúc field sau khi kết hợp |
| Query vẫn chậm dù đã dùng fragment | Fragment chỉ tái sử dụng selection set, không tối ưu resolver hoặc database | Đo resolver, xử lý N+1 và tối ưu truy vấn backend |
| Response thiếu field | Directive `@include` hoặc `@skip` loại bỏ field theo variable | Kiểm tra giá trị variable và điều kiện directive |

## 12. Checklist thiết kế fragment

- [ ] Fragment có tên rõ nghĩa, phản ánh nhóm dữ liệu được tái sử dụng.
- [ ] Type condition phù hợp với kiểu tại vị trí spread.
- [ ] Field riêng của union hoặc interface được đặt trong fragment phù hợp.
- [ ] Operation gửi lên server có đầy đủ fragment definition.
- [ ] Variable dùng trong fragment được khai báo ở operation sử dụng fragment.
- [ ] Không có fragment spread vòng lặp hoặc fragment không được sử dụng.
- [ ] Directive được dùng đúng vị trí và không bị nhầm với cơ chế phân quyền.
- [ ] Fragment không gom quá nhiều field gây overfetching.
- [ ] Các thay đổi schema được rà soát với fragment đang sử dụng.
- [ ] Operation có fragment được kiểm thử bằng GraphQlTester hoặc công cụ tương đương.

## Kết luận

Fragment là cơ chế tái sử dụng selection set trong GraphQL executable document. Named fragment giúp dùng lại một nhóm field có type condition rõ ràng; inline fragment giúp chọn field theo object type cụ thể, đặc biệt khi làm việc với interface và union. Client có thể kết hợp fragment với variables và directives để tổ chức operation linh hoạt.

Trong Spring for GraphQL, fragment được xử lý như một phần của GraphQL document. Các resolver vẫn được ánh xạ theo field trong schema bằng `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping`; không cần viết resolver riêng cho fragment. Sử dụng fragment có chủ đích giúp query dễ đọc và dễ bảo trì, đồng thời vẫn cần kiểm soát selection set, chi phí resolver, phân quyền và kiểm thử như mọi GraphQL operation khác.
