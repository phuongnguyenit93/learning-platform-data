# TypeResolver trong Spring for GraphQL

GraphQL interface và union cho phép một field trả về nhiều kiểu object cụ thể. Khi server thực thi query, nó cần biết object Java đang có trong tay tương ứng với GraphQL object type nào. `TypeResolver` đảm nhiệm việc xác định kiểu cụ thể đó tại runtime.

Trong Spring for GraphQL, ta có thể đăng ký `TypeResolver` thông qua `RuntimeWiringConfigurer`. Resolver nhận object nguồn từ kết quả của data fetcher và trả về `GraphQLObjectType` phù hợp trong schema. Việc ánh xạ này giúp GraphQL chọn đúng inline fragment, serialize đúng field và cung cấp giá trị `__typename` chính xác.

## 1. Vì sao cần TypeResolver?

Một field có kiểu object cụ thể thì GraphQL đã biết cấu trúc trả về. Ví dụ `book: Book` luôn trả về object type `Book`. Nhưng nếu field có kiểu interface hoặc union, kết quả có thể là một trong nhiều object type.

Ví dụ một chức năng tìm kiếm có thể trả về sách hoặc tác giả:

```graphql
interface SearchResult {
    id: ID!
}

type Book implements SearchResult {
    id: ID!
    title: String!
}

type Author implements SearchResult {
    id: ID!
    name: String!
}

union SearchHit = Book | Author

type Query {
    searchResults(keyword: String!): [SearchResult!]!
    searchHits(keyword: String!): [SearchHit!]!
}
```

`SearchResult` là interface vì hai kiểu `Book` và `Author` cùng có field `id`. `SearchHit` là union vì nó biểu diễn một kết quả có thể là `Book` hoặc `Author`, nhưng không định nghĩa field chung. Cả interface và union đều cần được phân giải thành một object type cụ thể khi GraphQL hoàn tất kết quả.

Nếu data fetcher trả về một Java object `Book`, GraphQL phải biết object đó là GraphQL type `Book`; nếu trả về `Author`, nó phải chọn GraphQL type `Author`. `TypeResolver` thực hiện bước xác định này.

## 2. TypeResolver nhận và trả về gì?

Trong GraphQL Java, `TypeResolver` là một hàm nhận `TypeResolutionEnvironment` và trả về `GraphQLObjectType`:

```java
import graphql.schema.TypeResolver;

TypeResolver resolver = environment -> {
    Object source = environment.getObject();

    if (source instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }

    if (source instanceof Author) {
        return environment.getSchema().getObjectType("Author");
    }

    throw new IllegalStateException("Unsupported runtime type");
};
```

Các thành phần chính:

- `environment.getObject()` trả về object nguồn mà data fetcher đã cung cấp cho field interface hoặc union.
- `environment.getSchema()` cho phép truy cập schema GraphQL đang thực thi.
- `getObjectType("Book")` lấy GraphQL object type có tên `Book` trong schema.
- Giá trị trả về phải là một object type hợp lệ đối với interface hoặc union đang được phân giải.

Với interface, object type được chọn phải implement interface đó. Với union, object type được chọn phải là một trong các member được khai báo trong union. Không được trả về một type tùy ý hoặc một type không thuộc tập kiểu được phép.

## 3. Chuẩn bị các kiểu Java nguồn

Ví dụ dùng Java record và sealed interface để mô hình hóa các kết quả tìm kiếm:

```java
public sealed interface SearchItem permits Book, Author {
    String id();
}

public record Book(String id, String title) implements SearchItem {
}

public record Author(String id, String name) implements SearchItem {
}
```

`Book` và `Author` là hai kiểu Java cụ thể. Cả hai implement `SearchItem`, nên service có thể trả về một danh sách dùng chung:

```java
import java.util.List;

public interface SearchService {
    List<SearchItem> search(String keyword);
}
```

Ở ví dụ này, `SearchItem` là abstraction của domain Java. Nó không tự động trở thành GraphQL interface; quan hệ giữa Java object và GraphQL object type được xác định bằng `TypeResolver` đã đăng ký trong runtime wiring.

Nếu dự án dùng Java phiên bản chưa hỗ trợ sealed interface hoặc record, có thể thay bằng interface và các class thông thường. Điều quan trọng là resolver có thể nhận diện từng kiểu object cụ thể, chẳng hạn bằng `instanceof` hoặc một thuộc tính phân loại đáng tin cậy.

## 4. Đăng ký TypeResolver bằng RuntimeWiringConfigurer

Spring for GraphQL cho phép cung cấp `RuntimeWiringConfigurer` dưới dạng Spring bean. Spring Boot sẽ dùng configurer này khi xây dựng GraphQL runtime wiring.

Ví dụ đăng ký cùng một `TypeResolver` cho cả interface `SearchResult` và union `SearchHit`:

```java
import graphql.schema.TypeResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfig {

    @Bean
    RuntimeWiringConfigurer searchTypeResolverConfigurer() {
        TypeResolver searchTypeResolver = environment -> {
            Object source = environment.getObject();

            if (source instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }

            if (source instanceof Author) {
                return environment.getSchema().getObjectType("Author");
            }

            throw new IllegalStateException("Unsupported SearchItem runtime type");
        };

        return builder -> builder
                .type("SearchResult", type -> type.typeResolver(searchTypeResolver))
                .type("SearchHit", type -> type.typeResolver(searchTypeResolver));
    }
}
```

`type("SearchResult", ...)` cấu hình wiring cho interface có tên `SearchResult`. Dòng tiếp theo đăng ký resolver cho union `SearchHit`. Vì cả hai có cùng các object member `Book` và `Author`, chúng có thể dùng chung logic phân loại.

Nếu interface và union có tập member khác nhau, hãy đăng ký resolver phù hợp cho từng type. Một resolver dùng chung chỉ an toàn khi các kiểu mà nó trả về đều hợp lệ trong mọi interface/union được gắn resolver đó.

## 5. Resolver trả về interface hoặc union

Controller có thể trả về danh sách các object Java cụ thể thông qua một kiểu chung:

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
    public List<SearchItem> searchResults(@Argument("keyword") String keyword) {
        return searchService.search(keyword);
    }

    @QueryMapping
    public List<SearchItem> searchHits(@Argument("keyword") String keyword) {
        return searchService.search(keyword);
    }
}
```

`@QueryMapping` ánh xạ method vào field của root `Query`. Method trả về các object Java thực tế; khi GraphQL cần hoàn tất từng phần tử có kiểu interface hoặc union, `TypeResolver` sẽ xác định object type tương ứng.

Trong ví dụ, hai method dùng cùng service để làm rõ cách ánh xạ. Ứng dụng thực tế có thể dùng hai service hoặc hai phương thức riêng nếu kết quả tìm kiếm của interface và union khác nhau.

## 6. Client truy vấn bằng inline fragments

Với interface, client có thể chọn các field chung được khai báo trên interface, sau đó dùng inline fragment để lấy field riêng của từng object type:

```graphql
query {
    searchResults(keyword: "spring") {
        __typename
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

Với union, client chỉ có thể chọn trực tiếp các meta-field được phép như `__typename`; các field cụ thể phải nằm trong inline fragment:

```graphql
query {
    searchHits(keyword: "spring") {
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

Một response minh họa:

```json
{
  "data": {
    "searchResults": [
      {
        "__typename": "Book",
        "id": "book-1",
        "title": "Spring GraphQL"
      },
      {
        "__typename": "Author",
        "id": "author-1",
        "name": "Nguyen An"
      }
    ],
    "searchHits": [
      {
        "__typename": "Book",
        "id": "book-1",
        "title": "Spring GraphQL"
      },
      {
        "__typename": "Author",
        "id": "author-1",
        "name": "Nguyen An"
      }
    ]
  }
}
```

`__typename` là meta-field do GraphQL cung cấp, không cần khai báo trong SDL. Giá trị của nó cho biết object type cụ thể mà `TypeResolver` đã chọn. Client thường dùng giá trị này để phân nhánh khi hiển thị dữ liệu hoặc xử lý kết quả polymorphic.

## 7. Phân biệt TypeResolver với data fetcher và SchemaMapping

Ba thành phần có nhiệm vụ khác nhau:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `@QueryMapping` / data fetcher | Lấy dữ liệu cho field, ví dụ truy vấn danh sách kết quả tìm kiếm. |
| `@SchemaMapping` | Lấy giá trị cho một field cụ thể của object, ví dụ `Book.author`. |
| `TypeResolver` | Xác định object type GraphQL cụ thể cho một giá trị đang được trả về qua interface hoặc union. |

Ví dụ `searchResults` trả về một danh sách object. Data fetcher tìm và trả dữ liệu. `TypeResolver` quyết định từng phần tử là `Book` hay `Author`. Sau đó, các field trong selection set được hoàn tất bằng giá trị object và các data fetcher tương ứng nếu có.

`TypeResolver` không dùng để tải dữ liệu từ database, không thay thế `@QueryMapping`, và cũng không phải cơ chế phân quyền. Nếu một object đã được phân loại là `Book`, quyền truy cập vào field `Book.title` vẫn cần được kiểm tra bằng cơ chế bảo mật phù hợp của ứng dụng.

## 8. Xử lý trường hợp không phân giải được kiểu

Một số lỗi thường gặp khi dùng TypeResolver:

- Data fetcher trả về một class Java mà resolver không nhận diện.
- Resolver trả về tên GraphQL type không tồn tại trong schema.
- Resolver trả về object type không implement interface đang dùng.
- Resolver trả về object type không nằm trong union member list.
- Một kiểu Java được dùng ở nhiều vị trí nhưng mỗi vị trí cần ánh xạ GraphQL type khác nhau.

Nên xử lý rõ trường hợp không hỗ trợ thay vì trả về null hoặc chọn một type mặc định tùy tiện. Ví dụ:

```java
TypeResolver searchTypeResolver = environment -> {
    Object source = environment.getObject();

    if (source instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }
    if (source instanceof Author) {
        return environment.getSchema().getObjectType("Author");
    }

    throw new IllegalStateException(
            "No GraphQL object type configured for search result");
};
```

Thông báo lỗi dành cho client nên được xử lý qua cơ chế GraphQL error của ứng dụng để không làm lộ chi tiết nội bộ. Log server có thể ghi thêm loại Java thực tế và ngữ cảnh request cần thiết để hỗ trợ điều tra.

Nếu một class Java có thể tương ứng với nhiều GraphQL object type tùy ngữ cảnh, chỉ kiểm tra `instanceof` có thể chưa đủ. Hãy dùng các subtype riêng biệt hoặc một discriminator trong domain model để quyết định type một cách rõ ràng. Không nên suy luận type từ dữ liệu do client kiểm soát nếu điều đó có thể khiến server phân loại sai object.

## 9. Kiểm thử TypeResolver với GraphQlTester

Kiểm thử cần xác nhận cả giá trị field cụ thể và `__typename`. Ví dụ với `GraphQlTester` đã được cấu hình trong test context:

```java
@Test
void interfaceResultResolvesConcreteTypes() {
    graphQlTester.document("""
            query {
                searchResults(keyword: "spring") {
                    __typename
                    id
                    ... on Book { title }
                    ... on Author { name }
                }
            }
            """)
        .execute()
        .path("searchResults[0].__typename")
        .entity(String.class)
        .isEqualTo("Book");
}
```

Có thể viết test tương tự cho phần tử thứ hai để xác nhận `Author`, và kiểm tra các field `title` hoặc `name` được trả về đúng theo fragment. Với union, hãy kiểm tra `__typename` và các field chỉ có trong từng inline fragment.

Nên có các test bổ sung:

1. Mỗi Java subtype được ánh xạ đến đúng GraphQL object type.
2. Tất cả object type được trả về đều là member hợp lệ của interface/union.
3. `__typename` đúng với từng phần tử trong danh sách hỗn hợp.
4. Inline fragment chỉ trả field của object type tương ứng.
5. Kiểu Java không được hỗ trợ tạo GraphQL error rõ ràng và không làm lộ thông tin nhạy cảm.
6. Danh sách rỗng vẫn trả về đúng kết quả theo nullability đã khai báo.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thể resolve abstract type | Chưa đăng ký TypeResolver phù hợp hoặc runtime wiring chưa được áp dụng | Kiểm tra `RuntimeWiringConfigurer` và tên interface/union trong SDL. |
| Luôn nhận sai `__typename` | Điều kiện phân loại object bị sai hoặc quá rộng | Kiểm tra subtype thực tế và ánh xạ từng class cụ thể. |
| Inline fragment không trả field | Resolver chọn sai object type hoặc fragment không khớp kiểu thực tế | Kiểm tra tên GraphQL type và kết quả TypeResolver. |
| TypeResolver trả object type không hợp lệ | Type không implement interface hoặc không thuộc union | Chỉ trả về object type nằm trong tập kiểu cho phép. |
| Thêm subtype mới nhưng query lỗi | TypeResolver chưa được cập nhật để nhận diện subtype | Bổ sung mapping và test cho subtype mới. |
| Field con vẫn lỗi sau khi resolve type | TypeResolver chỉ xác định object type, không cung cấp dữ liệu field | Kiểm tra source object và data fetcher/`@SchemaMapping` của field đó. |

## 11. Checklist khi triển khai TypeResolver

1. Khai báo interface hoặc union và các object type cụ thể trong SDL.
2. Bảo đảm object type implement đầy đủ field của interface hoặc được liệt kê trong union.
3. Chọn cách nhận diện từng Java object cụ thể một cách ổn định.
4. Đăng ký TypeResolver bằng `RuntimeWiringConfigurer` cho đúng tên interface/union.
5. Chỉ trả về GraphQL object type hợp lệ với abstract type đang được resolve.
6. Xử lý rõ kiểu Java chưa được hỗ trợ.
7. Kiểm tra `__typename` và inline fragments bằng GraphQlTester.
8. Khi thêm subtype, cập nhật schema, mapping và test cùng lúc.

`TypeResolver` là cầu nối giữa object Java ở runtime và kiểu GraphQL cụ thể trong interface hoặc union. Khi mapping được đăng ký đúng và phản ánh đầy đủ các subtype của domain, client có thể truy vấn dữ liệu đa hình bằng inline fragments một cách nhất quán, còn server giữ được hợp đồng schema rõ ràng.
