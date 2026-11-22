# Union type trong GraphQL

**Union type** là một kiểu trừu tượng trong GraphQL cho phép một field trả về một trong nhiều object type khác nhau. Union hữu ích khi một thao tác tìm kiếm hoặc một field có thể trả về nhiều loại kết quả không có cùng một tập field chung.

Ví dụ, tìm kiếm toàn hệ thống có thể trả về `Book` hoặc `Author`. Client không cần gọi hai API riêng; một field GraphQL có thể trả về danh sách `SearchResult`, trong đó mỗi phần tử là một object thuộc một trong hai kiểu trên.

Trong Spring for GraphQL, schema khai báo union bằng SDL. Resolver trả về các object Java tương ứng, còn GraphQL Java cần xác định kiểu object cụ thể của từng giá trị tại runtime thông qua cơ chế type resolution.

## 1. Khai báo Union type trong SDL

Union được khai báo bằng từ khóa `union`, theo sau là tên union và danh sách object type thành viên được phân tách bằng dấu `|`:

```graphql
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
    search(keyword: String!): [SearchResult!]!
}
```

Trong ví dụ này:

- `SearchResult` là kiểu union.
- `Book` và `Author` là hai object type có thể xuất hiện trong kết quả.
- `search` trả về một danh sách luôn tồn tại; từng phần tử trong danh sách cũng phải là một object hợp lệ thuộc `SearchResult`.
- Mỗi phần tử thực tế có thể là `Book` hoặc `Author`.

Union chỉ chứa các **object type**. Không thể thêm scalar, enum, input object, interface hoặc một union khác làm thành viên. Các object type thành viên có thể có cấu trúc rất khác nhau; union không yêu cầu chúng khai báo cùng field.

## 2. Khi nào nên dùng Union?

Union phù hợp khi một field có thể trả về nhiều kiểu object khác nhau và những kiểu đó không có một tập field chung đủ ý nghĩa để mô hình hóa bằng interface.

Ví dụ một trang tìm kiếm có thể trả về:

```graphql
type Product {
    id: ID!
    name: String!
    price: Float!
}

type Article {
    id: ID!
    title: String!
    publishedAt: String
}

type Category {
    id: ID!
    label: String!
}

union SearchHit = Product | Article | Category

type Query {
    searchAll(keyword: String!): [SearchHit!]!
}
```

Một phần tử kết quả có thể là sản phẩm, bài viết hoặc danh mục. Các kiểu này có thể cùng có `id`, nhưng mỗi kiểu có những field nghiệp vụ riêng. Union chỉ nói rằng field trả về một trong các kiểu đó; nó không tạo ra một field `id` dùng chung.

Những trường hợp thường phù hợp với union:

- Kết quả tìm kiếm tổng hợp từ nhiều miền dữ liệu.
- Một field trả về nhiều dạng nội dung, ví dụ `TextMessage`, `ImageMessage` hoặc `FileMessage`.
- Một thao tác có thể trả về nhiều object kết quả khác nhau, ví dụ `PaymentSuccess` hoặc `PaymentChallenge`.
- Một feed chứa nhiều loại phần tử có cấu trúc riêng.

Nếu các kiểu có một tập field chung rõ ràng và cùng thể hiện một khái niệm, interface thường là lựa chọn phù hợp hơn.

## 3. Truy vấn Union bằng Inline Fragment

Client không thể truy cập trực tiếp các field riêng của thành viên union ở cấp union. Muốn lấy field của một kiểu cụ thể, cần dùng **inline fragment** với cú pháp `... on TypeName`:

```graphql
query Search($keyword: String!) {
    search(keyword: $keyword) {
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

GraphQL chỉ thực thi selection trong fragment phù hợp với kiểu runtime của phần tử:

- Nếu phần tử là `Book`, client nhận `id` và `title`.
- Nếu phần tử là `Author`, client nhận `id` và `name`.
- `__typename` cho biết tên object type cụ thể, chẳng hạn `Book` hoặc `Author`.

Một response minh họa:

```json
{
  "data": {
    "search": [
      {
        "__typename": "Book",
        "id": "book-01",
        "title": "GraphQL in Practice"
      },
      {
        "__typename": "Author",
        "id": "author-01",
        "name": "An Nguyen"
      }
    ]
  }
}
```

`__typename` là meta-field do GraphQL cung cấp trên object, interface và union. Nó đặc biệt hữu ích khi client cần phân biệt các dạng kết quả để hiển thị component phù hợp hoặc cập nhật cache.

### Named fragment

Nếu một fragment được dùng ở nhiều nơi, có thể đặt tên cho fragment:

```graphql
query Search($keyword: String!) {
    search(keyword: $keyword) {
        __typename
        ...BookFields
        ...AuthorFields
    }
}

fragment BookFields on Book {
    id
    title
}

fragment AuthorFields on Author {
    id
    name
}
```

Named fragment giúp tái sử dụng selection set và tổ chức query lớn dễ đọc hơn. Kiểu sau từ khóa `on` phải là một object type thành viên hợp lệ của union hoặc một kiểu có quan hệ hợp lệ theo quy tắc fragment của GraphQL.

## 4. Union khác Interface như thế nào?

Union và interface đều là kiểu trừu tượng, nhưng mô hình hóa hai quan hệ khác nhau:

| Tiêu chí | Union | Interface |
|---|---|---|
| Mục đích | Gom nhiều object type có thể thay thế nhau ở một field | Mô tả hợp đồng field chung mà nhiều object type cùng triển khai |
| Khai báo | `union SearchResult` với các object type thành viên | `interface Node { id: ID! }` |
| Field chung | Không khai báo field nghiệp vụ chung | Khai báo các field bắt buộc của interface |
| Truy vấn field chung | Phải dùng fragment theo object type | Có thể truy vấn trực tiếp field được interface khai báo |
| Quan hệ của object type | Object type là thành viên union | Object type khai báo `implements InterfaceName` |

Ví dụ interface:

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

type Query {
    node(id: ID!): Node
}
```

Với `Node`, client có thể truy vấn `id` trực tiếp vì đó là field của interface:

```graphql
query {
    node(id: "item-01") {
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
```

Nếu dùng union `SearchResult = Book | Author`, client không thể viết `search { id }` chỉ vì cả `Book` và `Author` đều có field `id`. Union không công bố field chung. Client phải đặt `id` bên trong từng inline fragment:

```graphql
search(keyword: "GraphQL") {
    ... on Book {
        id
        title
    }
    ... on Author {
        id
        name
    }
}
```

Chọn interface khi các kiểu cùng chia sẻ một hợp đồng; chọn union khi cần biểu diễn một tập lựa chọn object type mà không cần ép chúng có chung cấu trúc.

## 5. Resolver trong Spring for GraphQL

Resolver của field trả về union thường trả về object Java thuộc một trong các kiểu thành viên. Ví dụ:

```java
public record Book(String id, String title) {}

public record Author(String id, String name) {}
```

Service tìm kiếm có thể trả về một danh sách chứa cả hai loại object:

```java
@Controller
class SearchController {

    private final SearchService searchService;

    SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    List<Object> search(@Argument String keyword) {
        return searchService.search(keyword);
    }
}
```

Kiểu trả về `List<Object>` chỉ là cách biểu diễn tổng quát trong Java. Quan trọng là từng phần tử phải thực sự là một object tương ứng với một thành viên được khai báo trong `SearchResult`. Có thể dùng một kiểu cha chung trong Java hoặc một interface Java nếu thiết kế domain cần điều đó, nhưng GraphQL union vẫn có tập thành viên riêng được định nghĩa trong SDL.

### Xác định kiểu object tại runtime

GraphQL Java cần biết mỗi object Java tương ứng với GraphQL object type nào. Với union và interface, việc xác định này được thực hiện bằng `TypeResolver`.

Có thể đăng ký resolver cho `SearchResult` bằng `RuntimeWiringConfigurer`:

```java
@Configuration
class GraphQlTypeResolverConfiguration {

    @Bean
    RuntimeWiringConfigurer searchResultTypeResolver() {
        return wiringBuilder -> wiringBuilder.typeResolver(
            "SearchResult",
            environment -> {
                Object value = environment.getObject();

                if (value instanceof Book) {
                    return environment.getSchema().getObjectType("Book");
                }

                if (value instanceof Author) {
                    return environment.getSchema().getObjectType("Author");
                }

                throw new IllegalStateException(
                    "Unsupported SearchResult type: " + value.getClass().getName()
                );
            }
        );
    }
}
```

`environment.getObject()` là object Java thực tế do resolver field trả về. `TypeResolver` kiểm tra kiểu Java rồi trả về `GraphQLObjectType` tương ứng trong schema. Ví dụ trên ánh xạ `Book` sang GraphQL type `Book` và `Author` sang GraphQL type `Author`.

Nếu ứng dụng dùng một quy ước ánh xạ class name và GraphQL type name nhất quán, có thể dùng cơ chế type resolution theo tên lớp mà Spring for GraphQL cung cấp. Khi tên lớp không khớp, nhiều package cùng có lớp tên giống nhau hoặc cần ánh xạ phức tạp, đăng ký `TypeResolver` tường minh giúp kiểm soát rõ kết quả.

Không nên trả về `null` hoặc một object type không thuộc union khi không nhận diện được kiểu runtime. Hãy xử lý trường hợp không hỗ trợ một cách rõ ràng để lỗi được phát hiện sớm trong quá trình thực thi và kiểm thử.

## 6. Field resolver và TypeResolver khác nhau thế nào?

Hai cơ chế này cùng tham gia vào quá trình thực thi nhưng giải quyết hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Field resolver (`@QueryMapping`, `@SchemaMapping`) | Giá trị của field là gì? | Tìm kiếm và trả về danh sách object kết quả. |
| TypeResolver | Object runtime này thuộc GraphQL object type nào? | Object Java `Book` tương ứng với `Book` trong union. |

Luồng xử lý một field union có thể mô tả như sau:

```text
Query.search(keyword)
        |
        | Field resolver trả về List<Object>
        v
  [Book, Author, Book, ...]
        |
        | TypeResolver cho từng phần tử
        v
  [GraphQL Book, GraphQL Author, GraphQL Book, ...]
        |
        | Áp dụng inline fragment tương ứng
        v
  Kết quả theo selection set của client
```

`TypeResolver` không tải dữ liệu thay cho field resolver. Nó chỉ xác định kiểu cụ thể để GraphQL biết fragment nào phù hợp và field nào có thể được chọn trên object đó.

## 7. Nullability và danh sách Union

Union tuân theo quy tắc nullability giống các kiểu GraphQL khác. Ví dụ:

```graphql
type Query {
    search(keyword: String!): [SearchResult!]!
    optionalSearch(keyword: String!): [SearchResult!]
}
```

- `[SearchResult!]!`: field luôn trả về danh sách; danh sách rỗng được phép; từng phần tử không được `null`.
- `[SearchResult!]`: field có thể trả về `null`, nhưng nếu có danh sách thì từng phần tử không được `null`.

Nếu một phần tử là `null` trong list `[SearchResult!]`, toàn bộ list trở thành `null`. Nếu field là `[SearchResult!]!`, giá trị `null` của list tiếp tục lan truyền lên field cha theo quy tắc Non-null. Ngoài ra, nếu `TypeResolver` không xác định được kiểu hợp lệ cho một phần tử, quá trình phân giải kiểu phát sinh lỗi thực thi; cần kiểm tra response và log để tìm object không được hỗ trợ.

Thông thường, field tìm kiếm nên trả về danh sách rỗng khi không có kết quả nếu hợp đồng API muốn bảo đảm luôn có một list. Không nên dùng `null` thay cho danh sách rỗng nếu client không cần phân biệt hai trạng thái đó.

## 8. Kiểm thử Union type

Kiểm thử cần xác minh cả dữ liệu trả về và kiểu runtime được GraphQL nhận diện:

1. Khi service trả về `Book`, response có `__typename: "Book"` và fragment `Book` được thực thi.
2. Khi service trả về `Author`, response có `__typename: "Author"` và fragment `Author` được thực thi.
3. Khi danh sách có nhiều loại object, mỗi phần tử được phân loại đúng độc lập.
4. Khi service trả về một kiểu Java không thuộc union, ứng dụng ghi nhận lỗi phù hợp và không trả về một object type sai.
5. Khi không có kết quả, response tuân theo nullability đã khai báo cho field list.

Ví dụ kiểm thử bằng `GraphQlTester`:

```java
@GraphQlTest(SearchController.class)
class SearchControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    SearchService searchService;

    @Test
    void resolvesDifferentUnionMembers() {
        given(searchService.search("GraphQL")).willReturn(List.of(
            new Book("book-01", "GraphQL in Practice"),
            new Author("author-01", "An Nguyen")
        ));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    search(keyword: "GraphQL") {
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
            .execute();

        response.path("search[0].__typename").entity(String.class).isEqualTo("Book");
        response.path("search[0].title").entity(String.class).isEqualTo("GraphQL in Practice");
        response.path("search[1].__typename").entity(String.class).isEqualTo("Author");
        response.path("search[1].name").entity(String.class).isEqualTo("An Nguyen");
    }
}
```

Ví dụ minh họa cấu trúc test; các import, static import `given` và SDL cần được cung cấp trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Nếu kiểm thử `TypeResolver` riêng, có thể xây dựng schema/runtime wiring trong test và đưa lần lượt từng kiểu Java vào quá trình resolve.

## 9. Lỗi thường gặp

**Truy vấn field trực tiếp trên union.** Câu lệnh `search { id }` không hợp lệ chỉ vì mọi thành viên hiện tại đều có `id`. Union không công bố field chung; phải đặt field trong inline fragment theo từng object type.

**Quên `__typename` khi client cần phân biệt kết quả.** Nếu giao diện cần hiển thị mỗi kiểu kết quả theo component khác nhau, hãy lấy `__typename` để nhận biết kiểu runtime.

**Thiếu TypeResolver hoặc ánh xạ sai kiểu runtime.** Resolver field có thể trả về dữ liệu đúng nhưng GraphQL vẫn không biết object thuộc thành viên union nào. Kiểm tra cấu hình `TypeResolver` và tên GraphQL object type.

**Trả về kiểu Java không thuộc union.** Mọi giá trị runtime phải ánh xạ đến một object type đã liệt kê trong union. Nếu domain bổ sung một kiểu kết quả mới, cần cập nhật cả SDL và type resolution.

**Dùng union khi thực chất cần hợp đồng chung.** Nếu client luôn cần truy vấn một field như `id` mà không muốn lặp fragment, hãy cân nhắc interface.

**Nhầm TypeResolver với resolver field.** Field resolver tải hoặc tính giá trị; TypeResolver chỉ xác định object type cụ thể cho giá trị đã có.

**Bỏ qua nullability của list.** Kiểm tra cả khả năng list `null`, phần tử `null` và trường hợp không có kết quả. Những lựa chọn này ảnh hưởng trực tiếp đến response khi một phần tử không thể phân giải.

## Kết luận

Union type cho phép một field GraphQL trả về nhiều object type khác nhau mà không cần chúng có chung field. Client dùng inline fragment để truy vấn dữ liệu riêng của từng kiểu và `__typename` để nhận diện kiểu runtime. Trong Spring for GraphQL, field resolver trả về object Java, còn `TypeResolver` ánh xạ object đó đến GraphQL object type tương ứng. Hãy chọn union khi mô hình hóa nhiều dạng kết quả, dùng interface khi cần hợp đồng field chung và kiểm thử mọi thành viên của union.
