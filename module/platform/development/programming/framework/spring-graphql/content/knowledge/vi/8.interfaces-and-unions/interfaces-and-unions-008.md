# Inline fragment khi query trong GraphQL

GraphQL **interface** và **union** cho phép một field trả về nhiều kiểu object cụ thể. Khi client query một field có kiểu trừu tượng như vậy, selection set chỉ được chọn trực tiếp những field mà kiểu trừu tượng công bố. Để lấy thêm field riêng của từng object type, client dùng **inline fragment** với cú pháp `... on TypeName`.

Inline fragment giúp một query xử lý nhiều kiểu kết quả trong cùng response mà vẫn giữ schema có cấu trúc rõ ràng. Trong Spring for GraphQL, resolver trả về các object Java tương ứng; GraphQL runtime xác định concrete type để áp dụng đúng fragment và trả về các field được chọn.

## 1. Vì sao cần inline fragment?

Giả sử API thư viện có hai loại kết quả tìm kiếm: sách và bài viết. Cả hai đều có ID và tiêu đề, nhưng các field riêng khác nhau:

- Sách có `isbn` và `pages`.
- Bài viết có `source` và `publishedAt`.

Client muốn gọi một query tìm kiếm và nhận cả hai loại kết quả. Nếu field trả về một interface `SearchResult`, client có thể chọn các field chung của interface trực tiếp. Khi cần field riêng, client dùng inline fragment.

~~~graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
    pages: Int!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
    publishedAt: String!
}

type Query {
    search: [SearchResult!]!
}
~~~

Trong schema này, `id` và `title` là field của interface `SearchResult`, vì vậy client có thể chọn trực tiếp. `isbn`, `pages`, `source` và `publishedAt` chỉ tồn tại trên các object type cụ thể, nên cần fragment để chọn chúng.

## 2. Cú pháp inline fragment

Inline fragment có dạng:

~~~graphql
... on TypeName {
    fieldA
    fieldB
}
~~~

`TypeName` là type condition. Các field trong fragment chỉ được áp dụng khi object thực tế phù hợp với type condition đó.

Ví dụ query `search`:

~~~graphql
query SearchLibrary {
    search {
        id
        title
        ... on Book {
            isbn
            pages
        }
        ... on Article {
            source
            publishedAt
        }
    }
}
~~~

Khi một phần tử có runtime type là `Book`, GraphQL trả `id`, `title`, `isbn` và `pages`. Khi phần tử có runtime type là `Article`, GraphQL trả `id`, `title`, `source` và `publishedAt`.

Client không cần gửi hai request riêng cho sách và bài viết. Một query mô tả tất cả field cần lấy; GraphQL chỉ thực thi fragment phù hợp với từng object trong kết quả.

## 3. Interface và field có thể chọn trực tiếp

Interface định nghĩa một tập field mà mọi object type triển khai phải cung cấp. Vì vậy, client có thể chọn field chung trực tiếp trên interface mà không cần fragment.

~~~graphql
query SearchLibrary {
    search {
        id
        title
        ... on Book {
            isbn
        }
        ... on Article {
            source
        }
    }
}
~~~

Trong query này:

- `id` và `title` được chọn trực tiếp vì thuộc `SearchResult`.
- `isbn` chỉ được chọn khi phần tử là `Book`.
- `source` chỉ được chọn khi phần tử là `Article`.

Một interface có thể kế thừa interface khác, và một object type có thể triển khai nhiều interface nếu schema khai báo đầy đủ các field bắt buộc. Quy tắc chọn field vẫn như nhau: field được định nghĩa trên kiểu tĩnh hiện tại có thể chọn trực tiếp; field chỉ có ở kiểu cụ thể phải nằm trong fragment tương ứng.

## 4. Union yêu cầu inline fragment cho field của object

Union đại diện cho một trong nhiều object type. Khác với interface, union không định nghĩa các field nghiệp vụ chung. Do đó, client không thể chọn trực tiếp `id` hoặc `title` từ union nếu các field đó chỉ tồn tại trên các object type thành viên.

Khai báo union:

~~~graphql
union CatalogItem = Book | Article

type Query {
    catalog: [CatalogItem!]!
}
~~~

Query union bằng inline fragment:

~~~graphql
query Catalog {
    catalog {
        __typename
        ... on Book {
            id
            title
            isbn
            pages
        }
        ... on Article {
            id
            title
            source
            publishedAt
        }
    }
}
~~~

`__typename` là meta field do GraphQL cung cấp, trả về tên object type thực tế của từng phần tử. Client có thể dùng giá trị này để phân nhánh hiển thị hoặc giải mã response. Đây cũng là cách lấy thông tin kiểu chung hữu ích khi query union.

Không thể viết `catalog { id title }` nếu `catalog` có kiểu `[CatalogItem!]!`, vì union không khai báo các field đó. Phải đặt field bên trong fragment `... on Book` hoặc `... on Article`.

## 5. Kết hợp interface, union và __typename

`__typename` có thể được chọn trên object, interface và union. Với interface, client có thể chọn các field chung rồi thêm `__typename` để nhận biết object cụ thể:

~~~graphql
query SearchLibrary {
    search {
        __typename
        id
        title
        ... on Book {
            isbn
        }
        ... on Article {
            source
        }
    }
}
~~~

Ví dụ response rút gọn:

~~~json
{
    "data": {
        "search": [
            {
                "__typename": "Book",
                "id": "book-101",
                "title": "GraphQL thực hành",
                "isbn": "978-604-000-001"
            },
            {
                "__typename": "Article",
                "id": "article-204",
                "title": "Thiết kế API hiện đại",
                "source": "Engineering Journal"
            }
        ]
    }
}
~~~

Response chỉ có field được selection set yêu cầu. Phần tử `Book` không có `source`; phần tử `Article` không có `isbn`. Client nên dựa vào `__typename` để xác định nhánh dữ liệu và tránh giả định mọi phần tử có cùng field riêng.

## 6. Inline fragment với directive

Có thể kết hợp fragment với directive `@include` hoặc `@skip` để điều khiển việc lấy field theo biến của query.

~~~graphql
query SearchLibrary($includeBookDetails: Boolean!) {
    search {
        __typename
        id
        title
        ... on Book @include(if: $includeBookDetails) {
            isbn
            pages
        }
        ... on Article {
            source
        }
    }
}
~~~

Khi `includeBookDetails` là `true`, các field `isbn` và `pages` được lấy cho phần tử `Book`. Khi là `false`, fragment này bị bỏ qua. Directive không thay đổi schema hoặc type condition; nó chỉ quyết định selection có được thực thi trong operation hiện tại hay không.

Directive cũng có thể được đặt trên field bên trong fragment:

~~~graphql
... on Book {
    isbn
    pages @include(if: $includeBookDetails)
}
~~~

Nên dùng directive khi client thực sự cần lựa chọn field theo ngữ cảnh, chẳng hạn màn hình danh sách và màn hình chi tiết dùng chung một operation. Đừng dùng directive để thay thế phân quyền; client có thể tự tạo query khác và yêu cầu field trực tiếp.

## 7. Inline fragment và named fragment

GraphQL hỗ trợ named fragment để tái sử dụng selection set. Inline fragment và named fragment đều có thể có type condition, nhưng cách khai báo khác nhau.

Inline fragment:

~~~graphql
query SearchLibrary {
    search {
        id
        ... on Book {
            isbn
            pages
        }
    }
}
~~~

Named fragment:

~~~graphql
query SearchLibrary {
    search {
        id
        ...BookDetails
    }
}

fragment BookDetails on Book {
    isbn
    pages
}
~~~

So sánh:

| Tiêu chí | Inline fragment | Named fragment |
| --- | --- | --- |
| Cú pháp | `... on Book { ... }` | `...BookDetails` và định nghĩa riêng |
| Phạm vi tái sử dụng | Ngay tại vị trí khai báo | Có thể dùng lại ở nhiều selection set phù hợp type condition |
| Dễ đọc | Thuận tiện khi fragment ngắn, chỉ dùng một lần | Thuận tiện khi selection dài hoặc được dùng lại |
| Type condition | Nằm ngay trong inline fragment | Nằm ở phần định nghĩa fragment |

Có thể kết hợp hai cách trong cùng một query. Ví dụ dùng named fragment cho field chung của `Book` và inline fragment cho một field nhỏ chỉ cần ở một vị trí.

## 8. Query lồng nhau với nhiều cấp fragment

Type condition có thể được dùng ở nhiều cấp của selection set. Ví dụ một tìm kiếm trả về `SearchResult`, và mỗi `Book` có field `relatedItems` là danh sách union `CatalogItem`:

~~~graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
    pages: Int!
    relatedItems: [CatalogItem!]!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
}

union CatalogItem = Book | Article

type Query {
    search: [SearchResult!]!
}
~~~

Query có fragment lồng nhau:

~~~graphql
query SearchWithRelatedItems {
    search {
        __typename
        id
        title
        ... on Book {
            relatedItems {
                __typename
                ... on Book {
                    isbn
                    pages
                }
                ... on Article {
                    source
                }
            }
        }
        ... on Article {
            source
        }
    }
}
~~~

Ở cấp ngoài, fragment xác định phần tử của `search` là `Book` hay `Article`. Chỉ khi là `Book`, client mới query `relatedItems`. Ở cấp trong, mỗi phần tử của union lại được phân nhánh theo `Book` hoặc `Article`.

Query lồng nhau có thể tăng chi phí truy vấn và số lần resolver được gọi. Khi fragment chọn các field liên kết như `relatedItems`, cần chú ý batching, DataLoader, giới hạn độ sâu và độ phức tạp truy vấn để tránh N+1 hoặc truy vấn quá nặng.

## 9. Spring for GraphQL trả về concrete type cho interface và union

Inline fragment chỉ hoạt động đúng khi GraphQL runtime xác định được object type thực tế. Khi resolver trả về một giá trị có kiểu tĩnh là interface hoặc một kiểu trừu tượng, GraphQL Java cần `TypeResolver` để ánh xạ object Java thành tên object type trong schema.

Ví dụ Java model:

~~~java
import java.util.List;

public interface SearchResult {
    String id();
    String title();
}

public record Book(
        String id,
        String title,
        String isbn,
        int pages
) implements SearchResult {}

public record Article(
        String id,
        String title,
        String source,
        String publishedAt
) implements SearchResult {}

public interface SearchService {
    List<SearchResult> search();
}
~~~

Resolver trả về nhiều concrete object:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchResult> search() {
        return searchService.search();
    }
}
~~~

Spring for GraphQL hỗ trợ `ClassNameTypeResolver` để suy ra GraphQL object type từ tên lớp Java. Cách mặc định thuận tiện khi tên concrete class trùng với tên object type trong SDL, ví dụ Java class `Book` ánh xạ đến GraphQL type `Book`. Nếu Java class có tên khác hoặc cần quy tắc riêng, hãy cấu hình `TypeResolver` trong `RuntimeWiring` cho interface hoặc union tương ứng.

Ví dụ cấu hình mapping rõ ràng khi class Java có tên khác:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class GraphQlTypeResolverConfiguration {

    @Bean
    RuntimeWiringConfigurer searchTypeResolverConfigurer() {
        ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
        typeResolver.addMapping(BookView.class, "Book");
        typeResolver.addMapping(ArticleView.class, "Article");

        return wiring -> wiring
                .typeResolver("SearchResult", typeResolver)
                .typeResolver("CatalogItem", typeResolver);
    }
}
~~~

`BookView` và `ArticleView` ở đây là các lớp Java của ứng dụng; chúng có thể khác tên với GraphQL object type `Book` và `Article`. Nếu tên class đã khớp schema và resolver mặc định hoạt động đúng, không cần đăng ký mapping riêng.

## 10. Kiểm thử inline fragment bằng GraphQlTester

Nên kiểm tra query có trả đúng field theo concrete type và `__typename` có giá trị như mong đợi.

Ví dụ test cho interface `SearchResult`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@GraphQlTest(SearchController.class)
class InlineFragmentTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    SearchService searchService;

    @Test
    void resolvesFieldsForEachConcreteType() {
        given(searchService.search()).willReturn(List.of(
                new Book("book-101", "GraphQL thực hành", "978-604-000-001", 320),
                new Article("article-204", "Thiết kế API hiện đại",
                        "Engineering Journal", "2026-11-20")
        ));

        graphQlTester.document("""
                query {
                    search {
                        __typename
                        id
                        ... on Book {
                            isbn
                        }
                        ... on Article {
                            source
                        }
                    }
                }
                """)
            .execute()
            .path("search[0].isbn")
            .entity(String.class)
            .isEqualTo("978-604-000-001");

        graphQlTester.document("""
                query {
                    search {
                        __typename
                        ... on Article {
                            source
                        }
                    }
                }
                """)
            .execute()
            .path("search[1].source")
            .entity(String.class)
            .isEqualTo("Engineering Journal");
    }
}
~~~

Đoạn test minh họa cách kiểm tra một kết quả `Book` và một kết quả `Article`. `SearchService` là dependency được mock bằng `@MockitoBean`; `Book`, `Article` và `SearchService` cần nằm trong package test hoặc được import từ package tương ứng. Test slice cũng cần giữ cấu hình type resolver nếu ứng dụng có mapping tùy chỉnh.

Với union, nên có test tương tự để xác nhận mỗi object type thành viên được resolve đúng và field chỉ xuất hiện trong fragment phù hợp. Nếu query báo lỗi kiểu “Could not determine type” hoặc lỗi resolve abstract type, hãy kiểm tra `TypeResolver` trước khi kiểm tra selection set.

## 11. Lỗi thường gặp khi dùng inline fragment

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field không được nhận diện trên interface | Field chỉ có trên object type cụ thể | Đặt field trong `... on ConcreteType` |
| Query union báo field không tồn tại | Union không khai báo field nghiệp vụ chung | Dùng inline fragment cho từng member type và chọn `__typename` nếu cần phân biệt |
| Fragment không chạy cho phần tử | Runtime object type không khớp type condition | Kiểm tra concrete type và `TypeResolver` |
| GraphQL không xác định được abstract type | Chưa có hoặc cấu hình sai `TypeResolver` | Cấu hình mapping interface/union sang GraphQL object type |
| Field riêng trả null hoặc lỗi | Resolver/property fetcher của concrete type không cung cấp field đó | Kiểm tra Java model, getter/record accessor và field mapping |
| Fragment lồng nhau làm query chậm | Selection set đi sâu qua nhiều quan hệ | Dùng DataLoader/batching và giới hạn query complexity/depth |
| Dùng fragment như cơ chế bảo mật | Cho rằng client không query fragment thì field được bảo vệ | Thực hiện authorization ở resolver/service hoặc field-level security |

## 12. Bảo mật và hiệu năng khi chọn field qua fragment

Inline fragment chỉ quyết định field nào được chọn dựa trên runtime type. Nó không phải cơ chế phân quyền. Nếu `Book` có field `internalNotes`, việc đặt field đó trong fragment không ngăn client khác tự viết query để yêu cầu nó.

Với field nhạy cảm, cần kiểm tra quyền ở resolver hoặc tầng service. Có thể áp dụng method security, kiểm tra principal trong `GraphQLContext`, hoặc dùng cơ chế bảo mật theo field của Spring Security. Quyền truy cập phải được xác minh cho từng request và tài nguyên.

Fragment cũng không làm giảm số lần gọi resolver một cách tự động. Khi fragment chọn field liên kết, ví dụ `Book.author` hoặc `Book.relatedItems`, GraphQL vẫn thực thi data fetcher tương ứng cho các object phù hợp. Hãy dùng `@BatchMapping`, DataLoader hoặc cơ chế batching của service để tránh N+1; đồng thời giới hạn độ sâu và độ phức tạp của operation.

## 13. Quy trình viết query có inline fragment

Khi query một field trả về interface hoặc union, có thể thực hiện theo các bước:

1. Xem field trả về interface hay union và xác định các object type có thể xuất hiện.
2. Chọn trực tiếp các field được khai báo trên interface; với union, bắt đầu bằng `__typename`.
3. Thêm `... on TypeName` cho field chỉ có trên từng concrete object type.
4. Dùng named fragment nếu selection set dài hoặc được tái sử dụng; dùng inline fragment cho nhánh ngắn, cục bộ.
5. Thêm directive như `@include` hoặc `@skip` khi cần điều khiển field theo biến query.
6. Kiểm tra GraphQL runtime xác định đúng concrete type bằng `TypeResolver`.
7. Kiểm thử từng nhánh type, field riêng, quyền truy cập và chi phí resolver.

Inline fragment là cách GraphQL biểu diễn rõ ràng những field phụ thuộc vào kiểu object thực tế. Khi kết hợp đúng với interface, union, `__typename` và type resolution trong Spring for GraphQL, client có thể lấy nhiều dạng dữ liệu trong một query mà vẫn giữ selection set an toàn theo schema.

## Tài liệu tham khảo

- [GraphQL Specification — Type Refinement](https://spec.graphql.org/October2021/#sec-Type-Refinement)
- [GraphQL Specification — Interfaces](https://spec.graphql.org/October2021/#sec-Interfaces)
- [GraphQL Specification — Unions](https://spec.graphql.org/October2021/#sec-Unions)
- [Spring for GraphQL — Request Execution and Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
