# Inline fragment

GraphQL cho phép client chọn field theo cấu trúc dữ liệu mà server công bố. Với một object type cụ thể, client có thể chọn trực tiếp các field của object đó. Nhưng khi một field trả về interface hoặc union, kiểu object thực tế chỉ được xác định lúc thực thi. Client cần một cách để yêu cầu các field riêng của từng kiểu cụ thể. **Inline fragment** giải quyết tình huống này bằng cách giới hạn một selection set theo một kiểu dữ liệu cụ thể.

Inline fragment đặc biệt hữu ích khi API trả về kết quả tìm kiếm có nhiều loại object, hoặc khi một field trả về interface có nhiều implementation. Trong Spring for GraphQL, inline fragment là cú pháp ở phía client; server cần khai báo schema đúng, trả về object Java phù hợp và cấu hình type resolver để GraphQL xác định kiểu cụ thể khi cần.

## Cú pháp cơ bản

Inline fragment dùng ba dấu chấm, theo sau là type condition và selection set:

~~~graphql
... on Book {
  id
  title
}
~~~

Phần **on Book** là type condition. Nó nói rằng các field bên trong chỉ được chọn khi object đang xử lý có kiểu cụ thể là Book. Nếu object thuộc kiểu khác, nhánh này không áp dụng.

Một operation có thể có nhiều inline fragment:

~~~graphql
query SearchCatalog($text: String!) {
  search(text: $text) {
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

Nếu search trả về Book, GraphQL lấy id và title. Nếu trả về Author, GraphQL lấy id và name. Client mô tả cả hai khả năng trong cùng một operation mà không phải gọi endpoint riêng cho từng loại kết quả.

## Vì sao cần inline fragment?

Một object type có các field xác định. Nhưng interface và union mô tả một giá trị có thể là một trong nhiều object type:

- **Interface** quy định các field chung mà những object type triển khai phải có.
- **Union** cho phép một field trả về một trong nhiều object type mà không yêu cầu chúng có field chung.

Với interface, client có thể chọn trực tiếp các field thuộc hợp đồng chung. Với union, client chỉ có thể chọn các field đặc biệt được GraphQL hỗ trợ trên union, chẳng hạn __typename; các field của từng object cụ thể phải được chọn trong inline fragment.

Ví dụ schema cho một danh mục sách:

~~~graphql
interface Node {
  id: ID!
}

type Book implements Node {
  id: ID!
  title: String!
  author: Author
}

type Author implements Node {
  id: ID!
  name: String!
  books: [Book!]!
}

union SearchResult = Book | Author

type Query {
  node(id: ID!): Node
  search(text: String!): [SearchResult!]!
}
~~~

Book và Author đều triển khai Node nên có field id. Tuy nhiên, title chỉ có trên Book, còn name chỉ có trên Author. Union SearchResult cho phép kết quả tìm kiếm chứa cả sách lẫn tác giả.

## Inline fragment với interface

Khi field trả về interface, client có thể truy vấn field chung mà không cần fragment. Inline fragment được dùng khi muốn chọn field chỉ tồn tại trên một implementation:

~~~graphql
query FindNode($id: ID!) {
  node(id: $id) {
    id
    __typename
    ... on Book {
      title
      author {
        id
        name
      }
    }
    ... on Author {
      name
      books {
        id
        title
      }
    }
  }
}
~~~

Field id được khai báo trên Node nên có thể chọn trực tiếp. Field title và author chỉ có trên Book; field name và books chỉ có trên Author nên phải đặt trong nhánh tương ứng.

Nếu node trả về một Book, response có thể như sau:

~~~json
{
  "data": {
    "node": {
      "id": "book-101",
      "__typename": "Book",
      "title": "Spring in Action",
      "author": {
        "id": "author-12",
        "name": "Craig Walls"
      }
    }
  }
}
~~~

Nếu node trả về Author, GraphQL áp dụng nhánh Author. Các field không thuộc nhánh phù hợp sẽ không xuất hiện trong response. Nhờ vậy, client nhận đúng dữ liệu theo kiểu thực tế mà không cần tự suy đoán từ những field nullable.

## Inline fragment với union

Union không định nghĩa field nghiệp vụ chung. Vì vậy, client không thể viết trực tiếp id, title hoặc name trên SearchResult dù các object member có thể chứa những field đó. Hãy sử dụng inline fragment:

~~~graphql
query Search($text: String!) {
  search(text: $text) {
    __typename
    ... on Book {
      id
      title
      author {
        name
      }
    }
    ... on Author {
      id
      name
      books {
        id
        title
      }
    }
  }
}
~~~

Giả sử kết quả có một quyển sách và một tác giả, response có thể là:

~~~json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-101",
        "title": "Spring in Action",
        "author": {
          "name": "Craig Walls"
        }
      },
      {
        "__typename": "Author",
        "id": "author-20",
        "name": "Jane Doe",
        "books": [
          {
            "id": "book-202",
            "title": "Reactive Systems"
          }
        ]
      }
    ]
  }
}
~~~

Mỗi phần tử có cấu trúc khác nhau vì GraphQL chỉ thực thi selection set phù hợp với kiểu cụ thể của phần tử đó. Các nhánh fragment không phải điều kiện lọc danh sách; chúng không loại bỏ object không khớp khỏi kết quả. Chúng chỉ quyết định field nào được lấy cho từng object.

## Field __typename

**__typename** là meta-field do GraphQL cung cấp. Nó trả về tên object type cụ thể đang được xử lý, ví dụ Book hoặc Author. Client có thể chọn __typename trên object, interface hoặc union mà không cần khai báo field này trong schema.

__typename thường được dùng cùng inline fragment vì client có thể dựa vào nó để phân biệt các loại kết quả:

~~~graphql
query Search($text: String!) {
  search(text: $text) {
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

Ở frontend, __typename hữu ích để render component đúng loại, phân biệt dữ liệu trong cache hoặc xử lý kết quả tìm kiếm đa hình. Ví dụ, client có thể hiển thị BookCard khi __typename là Book và AuthorCard khi __typename là Author.

Không nên dùng __typename như cơ chế phân quyền. Giá trị này chỉ cho biết kiểu object được trả về; quyền đọc field hoặc object vẫn phải được kiểm tra ở server.

## Inline fragment không có type condition

GraphQL cũng cho phép inline fragment không ghi **on Type**. Cách viết này nhóm các field vào một selection set và có thể gắn directive cho cả nhóm:

~~~graphql
query BookDetails($id: ID!, $includeReviews: Boolean!) {
  book(id: $id) {
    id
    title
    ... @include(if: $includeReviews) {
      reviews {
        id
        rating
      }
    }
  }
}
~~~

Trong ví dụ này, nhánh không có type condition vẫn áp dụng cho cùng object Book. Directive @include chỉ yêu cầu thực thi nhóm field reviews khi biến includeReviews là true. Directive @skip có tác dụng ngược lại: bỏ qua selection khi điều kiện của nó là true.

Inline fragment không có type condition hữu ích khi muốn áp dụng directive cho một nhóm field mà không cần lặp directive trên từng field. Khi có type condition, fragment còn thực hiện chức năng chọn field theo kiểu object cụ thể.

## Phân biệt inline fragment và named fragment

Named fragment là một selection set có tên, có thể tái sử dụng ở nhiều vị trí. Inline fragment viết trực tiếp selection set tại chỗ:

~~~graphql
fragment BookSummary on Book {
  id
  title
}

query Search($text: String!) {
  search(text: $text) {
    ...BookSummary
    ... on Author {
      id
      name
    }
  }
}
~~~

Trong ví dụ, BookSummary là named fragment có thể dùng lại ở nhiều operation hoặc selection set. Nhánh Author là inline fragment vì selection set chỉ được khai báo ngay tại vị trí sử dụng.

| Tiêu chí | Inline fragment | Named fragment |
| --- | --- | --- |
| Cách gọi | Viết selection set trực tiếp sau dấu ba chấm | Dùng fragment spread với tên fragment |
| Tái sử dụng | Thường dùng tại một vị trí | Có thể dùng ở nhiều vị trí |
| Type condition | Có thể có hoặc không | Bắt buộc có |
| Phù hợp | Nhánh ngắn, riêng cho một chỗ hoặc nhóm field có directive | Nhóm field dùng chung ở nhiều query |

Cả hai cách đều được GraphQL kiểm tra theo schema. Fragment phải có type condition tương thích với kiểu cha tại vị trí sử dụng; GraphQL từ chối operation nếu hai tập kiểu không thể giao nhau.

## Kết hợp inline fragment với directive

Các directive chuẩn @include và @skip có thể gắn vào inline fragment để bật hoặc bỏ qua một nhánh dựa trên biến:

~~~graphql
query Search(
  $text: String!
  $showBookDetails: Boolean!
  $showAuthorDetails: Boolean!
) {
  search(text: $text) {
    __typename
    ... on Book @include(if: $showBookDetails) {
      id
      title
    }
    ... on Author @include(if: $showAuthorDetails) {
      id
      name
    }
  }
}
~~~

Client có thể điều chỉnh các nhóm field theo nhu cầu màn hình mà không cần xây dựng nhiều operation gần giống nhau. Tuy nhiên, directive không thay thế pagination hay giới hạn độ phức tạp query. Server vẫn cần kiểm soát chi phí thực thi và xác thực quyền truy cập của từng field được chọn.

## GraphQL xác định kiểu cụ thể như thế nào?

Khi resolver trả về một object type trực tiếp như Book, GraphQL đã biết kiểu cụ thể từ khai báo field. Nhưng với interface hoặc union, GraphQL chỉ biết field trả về một kiểu trừu tượng. Khi thực thi, runtime phải xác định object Java hiện tại tương ứng với object type GraphQL nào.

GraphQL Java sử dụng **TypeResolver** cho interface và union. Type resolver nhận object nguồn và xác định GraphQL object type cụ thể. Spring for GraphQL cung cấp **ClassNameTypeResolver** để ánh xạ class Java sang tên object type; có thể khai báo mapping tường minh để tránh phụ thuộc vào quy ước tên lớp.

Ví dụ model Java:

~~~java
public interface SearchResult {
}

public record Book(String id, String title) implements SearchResult {
}

public record Author(String id, String name) implements SearchResult {
}
~~~

Resolver tìm kiếm trả về danh sách các object cụ thể:

~~~java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search(@Argument String text) {
        return searchService.search(text);
    }
}
~~~

Đăng ký type resolver cho interface và union:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlTypeConfiguration {

    @Bean
    RuntimeWiringConfigurer typeResolverConfigurer() {
        ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
        typeResolver.addMapping(Book.class, "Book");
        typeResolver.addMapping(Author.class, "Author");

        return builder -> {
            builder.typeResolver("Node", typeResolver);
            builder.typeResolver("SearchResult", typeResolver);
        };
    }
}
~~~

Trong cấu hình này, khi runtime gặp Book, resolver trả về GraphQL object type Book; khi gặp Author, resolver trả về Author. Cùng một type resolver có thể được đăng ký cho interface Node và union SearchResult nếu hai kiểu trừu tượng cùng chứa các object member phù hợp. Nếu model phức tạp hơn, có thể viết TypeResolver riêng để quyết định kiểu dựa trên class, thuộc tính phân biệt hoặc quy tắc domain.

Tên trong mapping phải khớp với object type trong SDL. Các object member cũng phải nằm trong tập kiểu có thể có của interface hoặc union. Nếu type resolver trả về kiểu không hợp lệ hoặc không thể xác định kiểu cụ thể, GraphQL không thể hoàn tất việc thực thi các nhánh inline fragment như mong đợi.

## Kiểm tra operation và lỗi thường gặp

Inline fragment được kiểm tra trước khi resolver thực thi. Một số lỗi thường gặp:

- Dùng field không tồn tại trên object type trong type condition.
- Viết type condition không thuộc tập kiểu có thể có của interface hoặc union.
- Chọn trực tiếp field riêng của một member trên union thay vì đặt trong inline fragment.
- Resolver trả về object Java không có mapping sang kiểu GraphQL cụ thể.
- SDL khai báo interface hoặc union nhưng runtime chưa đăng ký type resolver phù hợp.

Ví dụ sai:

~~~graphql
query Search {
  search(text: "Spring") {
    title
  }
}
~~~

Nếu search trả về union SearchResult, title không phải field trực tiếp của union. Cách đúng là:

~~~graphql
query Search {
  search(text: "Spring") {
    ... on Book {
      title
    }
  }
}
~~~

Khi debug, hãy kiểm tra lần lượt schema, kiểu Java resolver trả về, cấu hình TypeResolver và operation client gửi. Có thể thêm __typename vào selection set để quan sát runtime đang trả về kiểu object nào.

## Bảo mật và hiệu năng khi dùng inline fragment

Inline fragment chỉ chọn field dựa trên kiểu object. Nó không tự kiểm tra quyền người dùng và không làm cho field nhạy cảm trở nên an toàn. Các field trong mỗi nhánh vẫn cần được bảo vệ bằng Spring Security, method security, kiểm tra quyền trong resolver hoặc service và điều kiện truy cập dữ liệu phù hợp.

Một operation có nhiều nhánh fragment có thể yêu cầu nhiều field lồng nhau. Server vẫn phải tính đến độ sâu, độ phức tạp, pagination, batching và thời gian thực thi. Không nên coi một nhánh fragment bị client bỏ qua là cơ chế giới hạn tài nguyên duy nhất; cần cấu hình giới hạn query ở runtime hoặc gateway theo chính sách của ứng dụng.

Khi kiểm thử GraphQL API với Spring for GraphQL, hãy bao phủ cả trường hợp trả về từng kiểu cụ thể, trường hợp interface hoặc union trả về null nếu schema cho phép, nhánh fragment phù hợp, nhánh không phù hợp, directive bật/tắt và lỗi type resolution. Với GraphQlTester, có thể kiểm tra __typename và các path của từng phần tử để xác nhận dữ liệu đúng loại.

Inline fragment giúp client khai thác an toàn và rõ ràng các schema đa hình. Type condition xác định field nào được chọn cho từng object, __typename cho biết kiểu cụ thể, còn TypeResolver giúp GraphQL Java nhận diện object Java tương ứng. Khi schema, resolver và type mapping nhất quán, Spring for GraphQL có thể trả về các cấu trúc dữ liệu đa dạng trong cùng một operation mà vẫn giữ hợp đồng API có kiểu rõ ràng.
