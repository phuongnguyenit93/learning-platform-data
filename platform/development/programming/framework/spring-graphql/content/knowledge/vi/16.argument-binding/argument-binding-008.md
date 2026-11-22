# Map arguments trong Spring for GraphQL

Trong GraphQL, mỗi field có thể nhận nhiều argument. GraphQL Java cung cấp các giá trị đó dưới dạng một map theo tên argument. Spring for GraphQL cho phép controller truy cập dữ liệu này bằng `@Argument` hoặc `@Arguments` với tham số kiểu `Map<String, Object>`.

Hai cách dùng map có phạm vi khác nhau:

- `@Argument("filter") Map<String, Object> filter` lấy **giá trị thô của một argument có tên `filter`**. Nếu argument là input object, map chứa các field của input object đó.
- `@Arguments Map<String, Object> arguments` lấy **toàn bộ map các argument của field đang được xử lý**. Mỗi key là tên argument ở cấp field; value có thể là scalar, list hoặc map lồng nhau.

Phân biệt hai trường hợp này rất quan trọng. Từ Spring for GraphQL 1.2, `@Argument Map<String, Object>` luôn bind một argument được chỉ định hoặc suy luận theo tên tham số. Muốn lấy tất cả argument của field, hãy dùng `@Arguments`.

## 1. GraphQL arguments được biểu diễn như thế nào?

Giả sử API tìm sách có một input object dùng làm bộ lọc:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input AuthorFilter {
    ids: [ID!]
    namePrefix: String
}

input BookFilter {
    keyword: String
    status: BookStatus
    author: AuthorFilter
}

type Query {
    searchBooks(
        filter: BookFilter
        includeArchived: Boolean! = false
        limit: Int! = 20
    ): [Book!]!
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
}
~~~

Client có thể gửi query:

~~~graphql
query SearchBooks {
    searchBooks(
        filter: {
            keyword: "Spring"
            status: PUBLISHED
            author: {
                ids: ["author-1", "author-2"]
                namePrefix: "An"
            }
        }
        includeArchived: false
        limit: 10
    ) {
        id
        title
        status
    }
}
~~~

Ở thời điểm resolver được gọi, các argument đã được GraphQL parse và coerce theo schema. Spring for GraphQL có thể bind một phần dữ liệu đó vào object Java, hoặc cung cấp map để controller tự xử lý.

Map nhận được là cấu trúc giá trị sau GraphQL coercion, không phải chuỗi JSON thô của HTTP request và cũng không chứa toàn bộ GraphQL document. Nó chỉ đại diện cho argument của field đang được thực thi.

## 2. Dùng @Argument Map để lấy một argument

Khi chỉ cần truy cập input object `filter`, khai báo `@Argument("filter") Map<String, Object>`:

~~~java
import java.util.Map;
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> searchBooks(
            @Argument("filter") Map<String, Object> filter
    ) {
        return bookService.search(toCriteria(filter));
    }
}
~~~

`BookService`, `Book` và hàm chuyển đổi `toCriteria` là các thành phần của ứng dụng; phần chuyển đổi map được minh họa ở mục 5. Ví dụ tập trung vào chữ ký handler và phạm vi dữ liệu mà `@Argument` bind.

Spring tìm argument tên `filter` và đưa giá trị của riêng argument đó vào tham số map. Với query ở phần trước, map `filter` có các key như `keyword`, `status` và `author`; nó không chứa `includeArchived` hoặc `limit` vì các giá trị đó là argument ngang cấp của `filter`.

Nếu tên tham số Java trùng tên argument và compiler lưu parameter name, có thể viết `@Argument Map<String, Object> filter`. Trong code cần ổn định qua cấu hình build, nên chỉ rõ tên bằng `@Argument("filter")` hoặc bảo đảm compiler bật `-parameters`.

## 3. Dùng @Arguments Map để lấy toàn bộ arguments

Nếu controller cần nhiều argument cấp field cùng lúc, dùng `@Arguments`:

~~~java
import java.util.Map;

import org.springframework.graphql.data.method.annotation.Arguments;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    @QueryMapping
    public String argumentNames(@Arguments Map<String, Object> arguments) {
        return arguments.keySet().stream().sorted()
                .collect(java.util.stream.Collectors.joining(","));
    }
}
~~~

SDL tương ứng cho method minh họa này có thể khai báo:

~~~graphql
type Query {
    argumentNames(
        filter: BookFilter
        includeArchived: Boolean! = false
        limit: Int! = 20
    ): String!
}
~~~

Với schema đã khai báo default value, GraphQL cung cấp giá trị sau khi áp dụng quy tắc default. Trong ví dụ, `includeArchived` và `limit` có thể được bỏ qua bởi client; resolver nhận giá trị mặc định theo schema khi argument đó được coerce.

`@Arguments Map<String, Object>` chứa map argument của field hiện tại. Với query tìm sách ở trên, cấu trúc giá trị có dạng:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "status": "PUBLISHED",
        "author": {
            "ids": ["author-1", "author-2"],
            "namePrefix": "An"
        }
    },
    "includeArchived": false,
    "limit": 10
}
~~~

Đây là cấu trúc minh họa để dễ hình dung. Giá trị enum bên trong map phụ thuộc vào enum coercing/runtime wiring của schema; không nên mặc định mọi enum luôn được biểu diễn bằng chuỗi nếu ứng dụng có cấu hình internal value riêng.

## 4. Phân biệt @Argument Map và @Arguments Map

Hai cách viết đều nhận `Map<String, Object>`, nhưng chúng bind hai phạm vi khác nhau:

| Khai báo | Dữ liệu nhận được | Ví dụ key cấp đầu |
| --- | --- | --- |
| `@Argument("filter") Map<String, Object> filter` | Giá trị của argument `filter` | `keyword`, `status`, `author` |
| `@Arguments Map<String, Object> arguments` | Toàn bộ argument của field `searchBooks` | `filter`, `includeArchived`, `limit` |

Ví dụ với cùng một query:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") Map<String, Object> filter,
        @Argument("limit") Integer limit,
        @Argument("includeArchived") Boolean includeArchived
) {
    // Each @Argument binds one named argument.
}
~~~

So với:

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    // The map contains filter, limit, and includeArchived.
}
~~~

Không dùng `@Argument Map<String, Object>` với ý định lấy toàn bộ arguments. Trước Spring for GraphQL 1.2, một số cách dùng `@Argument` không chỉ rõ tên có hành vi trả về full arguments map; từ 1.2, `@Argument Map` luôn trả về raw value của argument được xác định theo tên annotation hoặc tên tham số. `@Arguments` là API dành cho full arguments map.

## 5. Truy cập map lồng nhau an toàn

Với input object có object con hoặc list, map có thể chứa các cấu trúc lồng nhau:

~~~json
{
    "author": {
        "ids": ["author-1", "author-2"],
        "namePrefix": "An"
    }
}
~~~

Không nên ép kiểu trực tiếp mà không kiểm tra dữ liệu. Một cách đọc an toàn hơn là kiểm tra kiểu tại mỗi cấp:

~~~java
import java.util.List;
import java.util.Map;

private Map<String, Object> asMap(Object value) {
    if (value == null) {
        return Map.of();
    }
    if (!(value instanceof Map<?, ?> source)) {
        throw new IllegalArgumentException("Expected an input object");
    }

    Map<String, Object> result = new java.util.HashMap<>();
    source.forEach((key, item) -> {
        if (!(key instanceof String name)) {
            throw new IllegalArgumentException("Expected string map keys");
        }
        result.put(name, item);
    });
    return result;
}

private List<String> stringList(Object value) {
    if (value == null) {
        return List.of();
    }
    if (!(value instanceof List<?> values)) {
        throw new IllegalArgumentException("Expected a list");
    }

    return values.stream()
            .map(item -> {
                if (!(item instanceof String text)) {
                    throw new IllegalArgumentException("Expected string values");
                }
                return text;
            })
            .toList();
}
~~~

Sau đó có thể chuyển map thành criteria object của ứng dụng:

~~~java
public record AuthorCriteria(List<String> ids, String namePrefix) {}

public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

public record BookSearchCriteria(
        String keyword,
        BookStatus status,
        AuthorCriteria author
) {}
~~~

~~~java
private BookSearchCriteria toCriteria(Map<String, Object> filter) {
    Map<String, Object> authorMap = asMap(filter.get("author"));

    AuthorCriteria author = new AuthorCriteria(
            stringList(authorMap.get("ids")),
            (String) authorMap.get("namePrefix")
    );

    return new BookSearchCriteria(
            (String) filter.get("keyword"),
            toBookStatus(filter.get("status")),
            author
    );
}

private BookStatus toBookStatus(Object value) {
    if (value == null) {
        return null;
    }
    if (value instanceof BookStatus status) {
        return status;
    }
    if (value instanceof String name) {
        return BookStatus.valueOf(name);
    }
    throw new IllegalArgumentException("Unsupported BookStatus value");
}
~~~

Đoạn chuyển đổi trên minh họa hai dạng enum value thường gặp: giá trị Java đã là `BookStatus` hoặc chuỗi tên enum. Nếu schema dùng internal value tùy chỉnh, hãy viết converter tương ứng thay vì dựa vào `toString()`.

## 6. Bind toàn bộ arguments vào một Java object bằng @Arguments

`@Arguments` không chỉ hỗ trợ `Map`. Có thể dùng nó để bind tất cả argument cấp field vào một record hoặc DTO có constructor phù hợp:

~~~java
public record SearchBooksArguments(
        BookFilter filter,
        Boolean includeArchived,
        Integer limit
) {}
~~~

Các input record tương ứng với SDL có thể khai báo như sau:

~~~java
public record AuthorFilter(List<String> ids, String namePrefix) {}

public record BookFilter(
        String keyword,
        BookStatus status,
        AuthorFilter author
) {}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(
            arguments.filter(),
            Boolean.TRUE.equals(arguments.includeArchived()),
            arguments.limit()
    );
}
~~~

Điểm khác biệt so với `@Argument BookFilter filter`:

- `@Argument("filter") BookFilter filter` bind riêng argument `filter` vào `BookFilter`.
- `@Arguments SearchBooksArguments arguments` bind map argument cấp field vào các thuộc tính của `SearchBooksArguments`.

Đây là lựa chọn phù hợp khi method nhận nhiều argument liên quan và muốn có kiểu Java rõ ràng. Nếu chỉ cần một input object, `@Argument` thường biểu đạt ý định trực tiếp hơn.

## 7. Khi nào nên dùng Map và khi nào nên dùng DTO?

Map linh hoạt nhưng làm giảm kiểm tra kiểu tại compile time. Với API ổn định và input có cấu trúc rõ ràng, DTO/record thường là lựa chọn tốt hơn.

| Tiêu chí | `Map<String, Object>` | DTO/record |
| --- | --- | --- |
| Kiểu dữ liệu | Kiểm tra thủ công khi đọc | Kiểu được khai báo trong Java |
| Cấu trúc lồng nhau | Phải kiểm tra và ép kiểu từng cấp | Binder có thể bind đệ quy sang object lồng nhau |
| Refactor | Tên key là chuỗi, dễ sai khi đổi tên | Compiler hỗ trợ tìm lỗi và refactor |
| Input linh hoạt | Thuận tiện khi xử lý filter động hoặc tập field thay đổi | Phù hợp với hợp đồng input ổn định |
| Validation | Thường cần kiểm tra thủ công hoặc chuyển sang DTO | Có thể dùng Bean Validation với `@Valid`/`@Validated` |
| Đọc code | Cần xem schema và key được truy cập | Chữ ký method thể hiện cấu trúc dữ liệu |

Map phù hợp khi:

- Một resolver cần xử lý bộ lọc động hoặc nhiều điều kiện tùy chọn.
- Cần chuyển tiếp một cấu trúc input linh hoạt đến lớp xử lý chuyên biệt.
- Cần đọc raw argument để thực hiện quy tắc chuyển đổi đặc thù.
- Đang xây dựng công cụ tổng quát hoạt động trên nhiều loại input object.

DTO/record phù hợp khi:

- Cấu trúc input đã ổn định và được định nghĩa rõ trong SDL.
- Muốn dùng Bean Validation.
- Muốn compiler hỗ trợ kiểm tra kiểu, đổi tên và refactor.
- Nhiều service cùng sử dụng một hợp đồng dữ liệu.

Không nên dùng map chỉ để tránh tạo một record nhỏ. Một kiểu input rõ ràng thường giúp controller và service dễ bảo trì hơn.

## 8. @Argument Map không bỏ qua GraphQL schema validation

Việc nhận argument bằng Map không biến GraphQL input thành dữ liệu tùy ý. GraphQL vẫn validate query và coerce input dựa trên SDL trước khi gọi resolver.

Ví dụ SDL:

~~~graphql
input BookFilter {
    keyword: String
    status: BookStatus
}

type Query {
    searchBooks(filter: BookFilter): [Book!]!
}
~~~

Nếu client gửi field `unknownField` không được khai báo trong `BookFilter`, GraphQL sẽ từ chối input object trong bước validation/coercion. Resolver không nhận một map tùy ý chứa field ngoài schema.

Map chỉ thay đổi cách Java nhận dữ liệu sau khi GraphQL đã xử lý hợp đồng schema. Vì vậy vẫn cần thiết kế input type có chủ đích, giới hạn kích thước list và kiểm soát các enum hoặc scalar được phép.

## 9. Phân biệt arguments với variables, context và source object

Trong một handler method, các khái niệm sau có phạm vi khác nhau:

| Dữ liệu | Cách truy cập | Ý nghĩa |
| --- | --- | --- |
| Một GraphQL argument | `@Argument("filter") Map<String, Object>` | Giá trị của một argument cụ thể |
| Tất cả arguments của field | `@Arguments Map<String, Object>` | Map các argument cấp field hiện tại |
| GraphQL variables | Thông qua argument sau coercion | Giá trị client truyền để thay thế biến trong operation; không phải một map riêng cần bind trực tiếp trong controller |
| Source/parent object | Tham số source, ví dụ `Book book` | Object cha đang được resolve cho field hiện tại |
| Request context | `GraphQLContext` hoặc `@ContextValue` | Metadata dùng chung như principal, tenant hoặc correlation ID |

Ví dụ query:

~~~graphql
query Search($criteria: BookFilter, $limit: Int!) {
    searchBooks(filter: $criteria, limit: $limit) {
        id
        title
    }
}
~~~

Khi resolver nhận `@Argument("filter") Map<String, Object> filter`, nó nhận giá trị đã được gắn vào argument `filter`, dù giá trị đó đến từ variable `$criteria`. Tên variable không trở thành tên key của argument map; key vẫn là tên argument `filter` theo schema.

## 10. Map và trường hợp omitted so với null

Với input nullable, GraphQL phân biệt việc client không gửi field và gửi field với giá trị `null`. Điều này thường quan trọng với mutation cập nhật một phần:

~~~graphql
input UpdateBookInput {
    title: String
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Ví dụ:

- `{ title: "New title" }`: cập nhật title, không đề cập subtitle.
- `{ title: "New title", subtitle: null }`: client yêu cầu xóa subtitle nếu nghiệp vụ cho phép.

Nếu cần biết chắc argument được bỏ qua hay được truyền `null`, nên dùng `ArgumentValue<T>` cho argument tương ứng. `@Argument` với một giá trị nullable đơn thuần không thể biểu đạt đầy đủ sự khác biệt này trong mọi trường hợp; `ArgumentValue` cung cấp `isOmitted()` cùng giá trị thực tế.

Với input object, `ArgumentValue` có thể được dùng làm thuộc tính của record Java để giữ thông tin field bị bỏ qua hay được truyền `null`:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

public record UpdateBookInput(
        String title,
        ArgumentValue<String> subtitle
) {}

@Controller
public class BookMutationController {

    @MutationMapping
    public Book updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input
    ) {
        if (input.subtitle().isOmitted()) {
            return bookService.keepSubtitle(id);
        }
        return bookService.setSubtitle(id, input.subtitle().value());
    }
}
~~~

SDL ở trên đã khai báo `UpdateBookInput.subtitle` là nullable. Nếu client bỏ qua `subtitle`, `isOmitted()` là `true` và service giữ nguyên giá trị cũ. Nếu client gửi `subtitle: null`, `isOmitted()` là `false` và `value()` trả `null`, cho phép service xóa giá trị nếu nghiệp vụ cho phép. Không nên dựa vào `Map.get(key) == null` để phân biệt hai trường hợp vì cách kiểm tra đó không phân biệt key vắng mặt và key có giá trị null; `containsKey` chỉ hữu ích khi cấu trúc map thực tế giữ lại sự khác biệt đó.

## 11. Validation khi nhận Map

GraphQL schema kiểm tra kiểu và nullability, nhưng không thay thế mọi quy tắc nghiệp vụ. Khi nhận map, controller hoặc service phải kiểm tra các điều kiện cần thiết trước khi sử dụng dữ liệu.

Ví dụ cần giới hạn danh sách tác giả:

~~~java
private AuthorCriteria toAuthorCriteria(Map<String, Object> authorMap) {
    List<String> ids = stringList(authorMap.get("ids"));

    if (ids.size() > 50) {
        throw new IllegalArgumentException("At most 50 author IDs are allowed");
    }

    String prefix = (String) authorMap.get("namePrefix");
    if (prefix != null && prefix.length() > 80) {
        throw new IllegalArgumentException("namePrefix is too long");
    }

    return new AuthorCriteria(ids, prefix);
}
~~~

Với input có cấu trúc ổn định, có thể bind vào record có constraint và dùng `@Valid`:

~~~java
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;

public record AuthorFilterInput(
        @Size(max = 50) List<String> ids,
        @Size(max = 80) String namePrefix
) {}

public record BookFilterInput(
        @Size(max = 120) String keyword,
        BookStatus status,
        @Valid AuthorFilterInput author
) {}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument("filter") @Valid BookFilterInput filter) {
    return bookService.search(filter);
}
~~~

Bean Validation cần validator được cấu hình trong application context. Dùng DTO giúp constraint được khai báo gần cấu trúc dữ liệu và tránh viết lại các kiểm tra kiểu thủ công trên map.

## 12. Bảo mật khi xử lý map arguments

Không đưa trực tiếp map từ client vào entity hoặc câu truy vấn database. Cách đó có thể tạo mass assignment, cho phép client thử truyền thuộc tính nội bộ hoặc điều kiện không được phép.

Một số nguyên tắc:

1. Chỉ đọc các key được schema và nghiệp vụ cho phép.
2. Dùng allowlist cho sort field, filter operation và trạng thái.
3. Không ghép key/value từ map trực tiếp vào SQL hoặc JPQL; dùng parameter binding và query builder an toàn.
4. Kiểm tra quyền truy cập ở service/resolver; map argument không phải bằng chứng authorization.
5. Giới hạn số lượng phần tử trong list, độ dài chuỗi và độ sâu input.
6. Không log toàn bộ map nếu có thể chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.

Nếu filter ảnh hưởng phạm vi tenant, hãy lấy tenant từ security principal hoặc context đã được xác thực và kết hợp với filter client gửi. Không cho client tự quyết định tenant chỉ bằng một key trong map nếu chưa kiểm tra quyền.

## 13. Kiểm thử Map arguments bằng GraphQlTester

Có thể dùng `@GraphQlTest` để kiểm tra resolver nhận đúng map từ GraphQL request. Ví dụ kiểm thử `@Argument("filter") Map`:

SDL cho test đặt trong `src/test/resources/graphql/schema.graphqls`:

~~~graphql
input BookFilter {
    keyword: String
}

type Query {
    filterKeyword(filter: BookFilter): String
    argumentSummary(filter: BookFilter, limit: Int): String
}
~~~

Controller nhận một argument hoặc toàn bộ arguments:

~~~java
import java.util.Map;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.Arguments;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class MapArgumentController {

    @QueryMapping
    public String filterKeyword(@Argument("filter") Map<String, Object> filter) {
        return (String) filter.get("keyword");
    }

    @QueryMapping
    public String argumentSummary(@Arguments Map<String, Object> arguments) {
        return arguments.keySet().stream().sorted()
                .collect(java.util.stream.Collectors.joining(","));
    }
}
~~~

Test xác nhận `@Argument` chỉ nhận input object `filter`, còn `@Arguments` nhìn thấy các argument cấp field:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(MapArgumentController.class)
class MapArgumentTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void distinguishesOneArgumentFromAllArguments() {
        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    filterKeyword(filter: { keyword: "Spring" })
                    argumentSummary(filter: { keyword: "Spring" }, limit: 10)
                }
                """)
            .execute();

        response.errors().verify();
        response.path("filterKeyword")
                .entity(String.class)
                .isEqualTo("Spring");
        response.path("argumentSummary")
                .entity(String.class)
                .isEqualTo("filter,limit");
    }
}
~~~

Test dùng một response để kiểm tra cả hai field. Nên bổ sung trường hợp nested map, list, giá trị null, argument bị bỏ qua, enum coercion và input không hợp lệ.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@Argument Map` chỉ chứa một object con | Annotation bind một named argument, không phải tất cả arguments | Dùng `@Arguments Map` nếu cần full map |
| Map không có key mong muốn | Dùng tên parameter không khớp argument hoặc thiếu `-parameters` | Khai báo `@Argument("name")` tường minh |
| `ClassCastException` khi đọc nested value | Giả định kiểu lồng nhau không đúng | Kiểm tra `instanceof` và validate trước khi ép kiểu |
| Giá trị enum không phải chuỗi mong đợi | Enum có internal value hoặc coercing tùy chỉnh | Kiểm tra runtime wiring hoặc bind vào kiểu enum/domain phù hợp |
| Không phân biệt được omitted và null | Chỉ kiểm tra `Map.get(...)` hoặc dùng nullable argument thông thường | Dùng `ArgumentValue<T>` cho giá trị cần phân biệt |
| `@Argument Map` trả kết quả khác code cũ | Hành vi trước 1.2 đã thay đổi | Từ 1.2, dùng `@Arguments` để lấy full arguments map |
| Input map chứa field lạ bị từ chối trước resolver | GraphQL schema không khai báo field đó | Bổ sung field vào SDL nếu hợp lệ; Map không bỏ qua schema validation |
| Map được gán thẳng vào entity gây cập nhật ngoài ý muốn | Tin dữ liệu client và dùng mass assignment | Chuyển map qua allowlist/criteria DTO trước khi gọi service |

## 15. Quy trình lựa chọn cách bind arguments

Khi viết annotated controller, có thể chọn theo thứ tự:

1. Nếu chỉ cần một argument, dùng `@Argument("name")` với kiểu scalar hoặc DTO phù hợp.
2. Nếu cần raw value của một input object, dùng `@Argument("input") Map<String, Object>`.
3. Nếu cần raw map của tất cả argument cấp field, dùng `@Arguments Map<String, Object>`.
4. Nếu cần bind tất cả argument vào một object có kiểu rõ ràng, dùng `@Arguments SearchArguments`.
5. Nếu input có cấu trúc ổn định và cần validation/refactor an toàn, ưu tiên record/DTO thay cho map.
6. Nếu cần phân biệt argument bị bỏ qua và truyền `null`, dùng `ArgumentValue<T>`.
7. Chuyển raw map thành criteria/domain object sau khi kiểm tra kiểu, key được phép và quy tắc nghiệp vụ.
8. Kiểm thử đúng phạm vi map, nested values, default values và trường hợp input không hợp lệ bằng `GraphQlTester`.

Map arguments hữu ích khi cần xử lý input linh hoạt, nhưng phải xác định rõ map đang đại diện cho một argument hay toàn bộ argument của field. Dùng đúng `@Argument` và `@Arguments`, kết hợp kiểm tra kiểu và chuyển đổi sang model có cấu trúc, giúp controller linh hoạt mà vẫn giữ schema GraphQL làm hợp đồng dữ liệu chính.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Argument API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/Argument.html)
- [Spring for GraphQL — Arguments API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/Arguments.html)
- [Spring for GraphQL — ArgumentValue API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/ArgumentValue.html)
