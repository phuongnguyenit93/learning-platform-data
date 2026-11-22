# GraphQL type resolution cho Interface và Union

Trong GraphQL, **type resolution** là quá trình xác định kiểu object cụ thể của một giá trị khi field trong schema trả về một kiểu trừu tượng (`interface` hoặc `union`). Schema cho client biết một field có thể trả về những kiểu nào; khi thực thi, server cần xác định object đang có thuộc kiểu cụ thể nào để GraphQL hoàn thành response đúng cách.

Ví dụ một chức năng tìm kiếm có thể trả về sách hoặc bài viết. Schema khai báo kết quả là `SearchResult`, nhưng khi server trả về một object, GraphQL phải biết object đó là `Book` hay `Article`. Spring for GraphQL sử dụng cơ chế type resolver của GraphQL Java để thực hiện bước này.

## Khi nào GraphQL cần type resolution?

Với một field có kiểu object cụ thể, chẳng hạn `Product`, GraphQL đã biết cấu trúc dữ liệu cần resolve. Nhưng một field có kiểu interface hoặc union có thể nhận nhiều kiểu object khác nhau. GraphQL phải xác định kiểu thực tế trước khi áp dụng các field selection tương ứng.

Ví dụ:

```graphql
interface SearchHit {
  id: ID!
  title: String!
}

type Book implements SearchHit {
  id: ID!
  title: String!
  isbn: String!
}

type Article implements SearchHit {
  id: ID!
  title: String!
  url: String!
}

union SearchResult = Book | Article

type Query {
  featured: [SearchHit!]!
  search(term: String!): [SearchResult!]!
}
```

`SearchHit` là interface quy định các field chung. `Book` và `Article` triển khai interface đó, đồng thời có field riêng. `SearchResult` là union cho biết kết quả tìm kiếm có thể là `Book` hoặc `Article`.

Khi resolver của `search` trả về một danh sách object Java, GraphQL cần xác định kiểu cụ thể của từng phần tử. Type resolution xảy ra ở thời điểm thực thi, sau khi operation đã được parse và validate theo schema.

## Interface và Union khác nhau như thế nào khi resolve?

Cả interface và union đều là abstract type, nhưng cách mô tả hợp đồng khác nhau:

| Đặc điểm | Interface | Union |
| --- | --- | --- |
| Mục đích | Mô tả các field chung mà nhiều object type phải cung cấp. | Gom các object type có thể khác nhau về cấu trúc vào một kiểu kết quả. |
| Thành viên | Object type triển khai interface bằng `implements`. | Danh sách thành viên được khai báo sau dấu `=`. |
| Field có thể chọn trực tiếp | Có thể chọn các field được khai báo trên interface. | Không có field nghiệp vụ chung; cần dùng fragment để chọn field của object cụ thể. |
| Type resolution | Xác định object type cụ thể triển khai interface. | Xác định object type cụ thể thuộc union. |

Với interface, client có thể chọn field chung rồi dùng inline fragment cho field riêng:

```graphql
query Featured {
  featured {
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
```

Với union, client dùng fragment để chọn field của từng thành viên:

```graphql
query Search($term: String!) {
  search(term: $term) {
    __typename
    ... on Book {
      id
      title
      isbn
    }
    ... on Article {
      id
      title
      url
    }
  }
}
```

`__typename` là meta-field của GraphQL, trả về tên object type cụ thể tại runtime. Nó đặc biệt hữu ích khi client nhận dữ liệu từ interface hoặc union và cần phân biệt từng trường hợp.

## Hai giai đoạn: validation và runtime resolution

Type resolution không thay thế schema validation. Hai bước có nhiệm vụ khác nhau:

1. **Validation:** GraphQL kiểm tra operation dựa trên schema. Ví dụ `isbn` chỉ được chọn trong fragment áp dụng cho `Book`; `url` chỉ được chọn trong fragment áp dụng cho `Article`.
2. **Runtime type resolution:** khi resolver trả về một object cho field có kiểu interface hoặc union, server xác định object đó là một kiểu thành viên hợp lệ. GraphQL dùng kiểu cụ thể để resolve các field trong selection set.

Ví dụ operation sau không hợp lệ vì `isbn` không phải field của interface `SearchHit` và không nằm trong fragment của `Book`:

```graphql
query InvalidFeatured {
  featured {
    id
    isbn
  }
}
```

Validation có thể phát hiện lỗi này trước khi gọi resolver. Ngược lại, nếu operation hợp lệ nhưng type resolver không xác định được object trả về là `Book` hay `Article`, lỗi chỉ xuất hiện trong quá trình thực thi.

## TypeResolver trong GraphQL Java

GraphQL Java cung cấp interface `TypeResolver` để ánh xạ một object runtime sang `GraphQLObjectType` trong schema. Resolver nhận một `TypeResolutionEnvironment`; từ đó có thể đọc object nguồn bằng `getObject()` và lấy kiểu object đã khai báo trong schema qua `getSchema()`.

Chiến lược phổ biến là kiểm tra kiểu Java của object:

```java
import graphql.schema.TypeResolver;

TypeResolver searchTypeResolver = environment -> {
    Object source = environment.getObject();

    if (source instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }

    if (source instanceof Article) {
        return environment.getSchema().getObjectType("Article");
    }

    return null;
};
```

Với object `Book`, resolver trả về `GraphQLObjectType` có tên `Book`. Với object `Article`, resolver trả về type `Article`. Nếu object không thuộc kiểu nào đã biết, resolver không thể xác định concrete type; trả về `null` sẽ khiến GraphQL báo lỗi type resolution trong quá trình thực thi.

Type resolver phải trả về một object type hợp lệ và là possible type của abstract type đang được resolve. Không nên trả về type bất kỳ chỉ vì tên type tồn tại trong schema.

## Đăng ký TypeResolver trong Spring for GraphQL

Spring for GraphQL cho phép đăng ký cấu hình GraphQL Java thông qua bean `RuntimeWiringConfigurer`. Có thể đăng ký type resolver cho interface và union trong cùng cấu hình:

```java
import graphql.schema.TypeResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer abstractTypeResolvers() {
        TypeResolver resolver = environment -> {
            Object source = environment.getObject();

            if (source instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }
            if (source instanceof Article) {
                return environment.getSchema().getObjectType("Article");
            }
            return null;
        };

        return builder -> {
            builder.type("SearchHit", type -> type.typeResolver(resolver));
            builder.type("SearchResult", type -> type.typeResolver(resolver));
        };
    }
}
```

`SearchHit` và `SearchResult` là hai abstract type trong SDL. Cả hai có cùng tập possible type trong ví dụ này nên có thể dùng chung chiến lược nhận diện `Book` và `Article`. Nếu interface và union có tập thành viên khác nhau, hãy đăng ký resolver phù hợp với từng abstract type.

Spring Boot/Spring for GraphQL thu thập bean `RuntimeWiringConfigurer` khi xây dựng `GraphQlSource`, sau đó áp dụng cấu hình này vào GraphQL Java runtime wiring. Vì vậy, không cần tự tạo một `GraphQLSchema` riêng chỉ để đăng ký resolver trong ứng dụng Spring Boot thông thường.

## Kết hợp resolver với controller mapping

Controller cung cấp dữ liệu cho field gốc; type resolver xác định kiểu cụ thể của từng object; sau đó các field resolver tiếp tục xử lý field được chọn trên object đó.

Ví dụ model Java đơn giản:

```java
public interface SearchHit {
    String getId();
    String getTitle();
}

public class Book implements SearchHit {
    private String id;
    private String title;
    private String isbn;

    // constructors and getters
}

public class Article implements SearchHit {
    private String id;
    private String title;
    private String url;

    // constructors and getters
}
```

Query controller có thể trả về các object khác kiểu trong cùng danh sách:

```java
@Controller
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @QueryMapping
    public List<SearchHit> featured() {
        return searchService.featured();
    }

    @QueryMapping
    public List<Object> search(@Argument String term) {
        return searchService.search(term);
    }
}
```

`featured()` trả về các object thực tế là `Book` hoặc `Article`, cả hai đều triển khai Java interface `SearchHit`. `search()` cũng có thể trả về một danh sách object hỗn hợp; kiểu khai báo Java của collection không thay thế type resolver của GraphQL.

Khi GraphQL đã xác định object là `Book`, field mapping dành cho `Book` có thể được áp dụng. Ví dụ:

```java
@SchemaMapping(typeName = "Book", field = "publisher")
public Publisher publisher(Book book) {
    return publisherService.findByBookId(book.getId());
}
```

`@SchemaMapping` ở đây xử lý field `publisher` của object type `Book`. Nó không quyết định object abstract ban đầu là `Book` hay `Article`; nhiệm vụ đó thuộc về type resolver.

## Dùng discriminator thay cho instanceof

Không phải ứng dụng nào cũng có class Java riêng cho từng GraphQL object type. Một số hệ thống dùng DTO tổng hợp, record, map hoặc dữ liệu từ dịch vụ bên ngoài. Khi đó, có thể dựa vào discriminator đã được xác thực trong dữ liệu:

```java
TypeResolver resolver = environment -> {
    SearchDocument document = (SearchDocument) environment.getObject();

    return switch (document.kind()) {
        case "BOOK" -> environment.getSchema().getObjectType("Book");
        case "ARTICLE" -> environment.getSchema().getObjectType("Article");
        default -> null;
    };
};
```

`kind` là thuộc tính do ứng dụng định nghĩa để phân loại object. Cần bảo đảm giá trị đó đến từ dữ liệu đáng tin cậy và chỉ ánh xạ tới những object type được phép trong schema. Không nên lấy trực tiếp tên type tùy ý từ input của client rồi dùng nó để chọn GraphQL object type.

Với hệ thống có nhiều loại kết quả, có thể tách logic nhận diện thành một service hoặc component để dễ kiểm thử và tránh lặp lại trong nhiều type resolver.

## Xử lý trường hợp không xác định được kiểu

Type resolution có thể thất bại trong một số trường hợp:

- Resolver trả về object không thuộc bất kỳ concrete type nào được khai báo cho interface hoặc union.
- Type resolver kiểm tra sai class hoặc discriminator.
- Schema đổi tên object type nhưng logic mapping chưa được cập nhật.
- Một object type được trả về nhưng không phải possible type của abstract type đang xử lý.
- Dữ liệu từ hệ thống ngoài thiếu hoặc có discriminator không hợp lệ.

Khi type resolver không trả về một kiểu hợp lệ, GraphQL phát sinh execution error. Giá trị null sẽ lan theo quy tắc nullability của field chứa abstract type. Ví dụ, nếu field là `[SearchResult!]!`, một phần tử không nullable không resolve được có thể khiến list trở thành null; do list cũng không nullable, null có thể lan tiếp lên field cha.

Không nên âm thầm ép object không nhận diện được thành một type mặc định. Cách đó có thể làm client nhận dữ liệu sai cấu trúc hoặc che giấu lỗi tích hợp. Hãy ghi log đủ ngữ cảnh kỹ thuật, không ghi dữ liệu nhạy cảm, và trả lỗi phù hợp theo cơ chế error handling của ứng dụng.

## Kiểm thử type resolution

Kiểm thử nên xác nhận cả hai nhánh interface/union và trường hợp dữ liệu không được nhận diện.

Ví dụ dùng `GraphQlTester` để kiểm tra union:

```java
@Test
void searchResolvesConcreteTypes() {
    graphQlTester.document("""
        query {
          search(term: "spring") {
            __typename
            ... on Book {
              id
              title
              isbn
            }
            ... on Article {
              id
              title
              url
            }
          }
        }
        """)
        .execute()
        .path("search[0].__typename")
        .entity(String.class)
        .isEqualTo("Book");
}
```

Test này giả định dữ liệu test đầu tiên của `search` là một `Book`. Nên có thêm test cho `Article`, interface `SearchHit`, danh sách trộn nhiều concrete type và object không được nhận diện. Với trường hợp lỗi, kiểm tra cả `errors` và cách null lan theo SDL.

Khi test cấu hình runtime wiring, nên khởi tạo ứng dụng hoặc `GraphQlSource` trong test để xác minh bean `RuntimeWiringConfigurer` thực sự được áp dụng. Chỉ test riêng hàm `instanceof` chưa đủ để chứng minh resolver đã được đăng ký vào schema đang chạy.

## Lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Báo không xác định được concrete type | Thiếu TypeResolver hoặc resolver không nhận diện object. | Đăng ký resolver cho interface/union và kiểm tra class/discriminator. |
| Fragment đúng schema nhưng field trả null | Runtime type được resolve sai hoặc object không cung cấp dữ liệu field. | Kiểm tra `__typename`, resolver và field mapping của concrete type. |
| TypeResolver trả về object type không hợp lệ | Type không thuộc possible types của interface/union. | Chỉ trả về các thành viên được khai báo trong SDL. |
| Interface hoạt động nhưng union lỗi | Chỉ đăng ký resolver cho interface, chưa đăng ký cho union. | Đăng ký type resolver riêng cho từng abstract type. |
| Field riêng của object không được trả về | Client chưa dùng inline fragment hoặc fragment không áp dụng cho concrete type. | Kiểm tra selection set và tên object type trong fragment. |
| Thay đổi tên class làm resolution hỏng | Logic dựa trên class hoặc discriminator không còn khớp. | Đồng bộ mapping với schema và bổ sung test runtime. |

Khi debug, hãy bắt đầu bằng cách thêm `__typename` vào query. Giá trị này cho biết GraphQL đã chọn concrete type nào. Sau đó kiểm tra SDL, possible types, object thực tế mà resolver trả về và cấu hình `RuntimeWiringConfigurer`.

## Ghi nhớ

GraphQL type resolution xác định concrete object type cho field trả về interface hoặc union. Interface cung cấp các field chung; union chỉ liệt kê các object type có thể xuất hiện. Client dùng inline fragment để chọn field riêng và `__typename` để biết kiểu thực tế.

Trong Spring for GraphQL, đăng ký `TypeResolver` thông qua `RuntimeWiringConfigurer`. Resolver thường dựa trên class Java hoặc discriminator đáng tin cậy để trả về `GraphQLObjectType` tương ứng. Sau khi concrete type được xác định, GraphQL mới áp dụng các field selection và mapping của object đó. Cần kiểm thử đầy đủ các kiểu thành viên và xử lý rõ trường hợp không nhận diện được kiểu.
